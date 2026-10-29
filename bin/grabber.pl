#!/usr/bin/perl
# Rituals2Lox  -  Grabber
# Called every minute by cron. Polls Rituals cloud API, sends UDP to Miniserver,
# and updates hubs_cache.json so the web UI shows live data without manual scan.

use strict;
use warnings;
use utf8;
use Encode qw(decode encode);
use LWP::UserAgent;
use HTTP::Request;
use JSON;
use IO::Socket::INET;
use LoxBerry::Log;

binmode(STDOUT, ':encoding(UTF-8)');

use constant {
    API_BASE    => 'https://rituals.apiv2.sense-company.com/apiv2',
    TOKEN_FILE  => 'REPLACELBPDATADIR/token.json',
    CONFIG_FILE => 'REPLACELBPDATADIR/config.json',
    CACHE_FILE  => 'REPLACELBPDATADIR/hubs_cache.json',
    HTTP_TIMEOUT => 15,
};

my $log = LoxBerry::Log->new( name => 'grabber', addtime => 1, loglevel => 6 );
LOGSTART("Rituals2Lox Grabber");

# -- Config ---------------------------------------------------------------------
my $cfg     = load_json(CONFIG_FILE);

# Get Miniserver config from LoxBerry's own system (no manual config needed)
# Falls back to manual config if set, then to no UDP
my $ms_ip   = '';
my $ms_port = 56069;

my %miniservers = LoxBerry::System::get_miniservers();
if (%miniservers && $miniservers{1}) {
    $ms_ip   = $miniservers{1}{IPAddress} // '';
    $ms_port = $miniservers{1}{Port}      // 56069;
    LOGINF("Using Miniserver from LoxBerry config: $ms_ip:$ms_port");
}

# Manual override from plugin config takes precedence
if ($cfg->{miniserver_ip}) {
    $ms_ip   = $cfg->{miniserver_ip};
    $ms_port = $cfg->{miniserver_port} // $ms_port;
    LOGINF("Using Miniserver from plugin config: $ms_ip:$ms_port");
}

unless ($ms_ip) {
    LOGWARN("No Miniserver configured  -  will update cache but skip UDP.");
}

# Feature flags from plugin config
my $enable_udp  = $cfg->{enable_udp}  // 0;
my $enable_http = $cfg->{enable_http} // 1;
LOGINF("UDP push: " . ($enable_udp ? "enabled" : "disabled") .
       "  /  HTTP state.cgi: " . ($enable_http ? "enabled" : "disabled"));


# -- Token ----------------------------------------------------------------------
my $token = read_token();
unless ($token) {
    LOGWARN("No valid token  -  skipping poll. Check token-manager log for details.");
    # Log token.json state for diagnosis
    if (-f TOKEN_FILE) {
        my $td = load_json(TOKEN_FILE);
        my $left = ($td->{expires_at} // 0) - time();
        LOGWARN("token.json exists: eva_token=" . (($td->{eva_token}//'') ? "present" : "MISSING") .
                "  expires_at=" . ($td->{expires_at}//0) .
                "  left=" . int($left/60) . " min");
    } else {
        LOGWARN("token.json does not exist.");
    }
    LOGEND; exit 0;
}
LOGINF("Token OK  -  proceeding with API poll.");

# -- HTTP client ----------------------------------------------------------------
my $ua = LWP::UserAgent->new( agent => 'Rituals2Lox/0.1', timeout => HTTP_TIMEOUT );

# -- Fetch hub list -------------------------------------------------------------
my $hubs_resp = $ua->get( API_BASE . '/account/hubs', Authorization => $token );
unless ($hubs_resp->is_success) {
    LOGWARN("Hub list HTTP " . $hubs_resp->code . ": " . $hubs_resp->status_line);
    LOGEND; exit 0;
}

my $hubs = eval { decode_json($hubs_resp->decoded_content) };
unless (ref $hubs eq 'ARRAY') {
    LOGWARN("Hub list response is not an array."); LOGEND; exit 0;
}

LOGINF("Found " . scalar(@$hubs) . " hub(s).");

# -- Poll each hub --------------------------------------------------------------
my @cache_hubs;  # accumulate for hubs_cache.json update

foreach my $entry (@$hubs) {
    my $hash    = $entry->{hash}   // next;
    my $hublot  = $entry->{hublot} // '';
    my $av      = $entry->{attributeValues} // {};
    my $fw      = $entry->{firmwareInfo}    // {};
    my $sensors_cap = $entry->{sensors}    // {};
    my $nfc     = $entry->{nextFanChange}  // {};

    # Live values from attributeValues
    my $fanc      = $av->{fanc}         // '0';
    my $speedc    = $av->{speedc}       // '0';
    my $room_name = $av->{roomnamec}    // $av->{fspacenamec} // $hublot;
    my $squarem   = $av->{squaremeterc} // '';
    my $roomtype  = $av->{fspacetypec}  // '';
    my $ledc      = $av->{ledc}         // '0';
    my $roomc     = $av->{roomc}        // '';
    my $online    = ($entry->{status}   // 0) ? 1 : 0;

    # Schedule info
    my $fan_state   = $nfc->{currentState}        // '';
    my $next_time   = $nfc->{nextStateChangeTime}  // '';
    my $next_val    = $nfc->{nextStateChangeValue};
    my $next_change = '';
    if ($next_time && defined $next_val) {
        $next_change = "$next_time (speed: $next_val)";
    } elsif ($fan_state) {
        $next_change = $fan_state;
    }

    LOGINF("Hub: '$room_name' ($hublot) fanc=$fanc speedc=$speedc online=$online");

    # -- Fetch sensor values ---------------------------------------------------
    my ($fill_t, $perfume_t, $wifi_t, $batt_t, $version_sensor, $wifi_desc)
        = ('', '', '', '', '', '');
    my %sensor_vars = (
        fillc    => \$fill_t,
        rfidc    => \$perfume_t,
        wific    => \$wifi_t,
        battc    => \$batt_t,
        versionc => \$version_sensor,
    );

    for my $sname (keys %sensor_vars) {
        next unless $sensors_cap->{$sname};
        my $sresp = $ua->get(
            API_BASE . "/hubs/$hash/sensors/$sname",
            Authorization => $token,
        );
        if ($sresp->is_success) {
            my $d = eval { decode_json($sresp->decoded_content) };
            if (!$@ && ref $d eq 'HASH') {
                my $val  = $d->{value} // $d->{title} // '';
                my $desc = $d->{description} // '';
                ${ $sensor_vars{$sname} } = $val;
                $wifi_desc = $desc if $sname eq 'wific' && $desc;
                LOGINF("  sensor $sname = '$val' ($desc)");
            }
        } else {
            LOGWARN("  sensor $sname HTTP " . $sresp->code);
        }
    }

    # -- Maps ------------------------------------------------------------------
    my %fill_map = (
        'Full'                     => 100,
        'Half'                     => 50,
        'Low'                      => 25,
        'Empty'                    => 0,
        'No measurement available' => -1,
    );
    my %wifi_map = ('High' => 100, 'Medium' => 50, 'Low' => 25);
    my %roomc_map = ('1'=>'Small','2'=>'Medium','3'=>'Large','4'=>'Extra Large');
    my %int_map   = ('1'=>'Low','2'=>'Medium','3'=>'High');

    my $hub_key   = sanitize($room_name);
    my $version   = $version_sensor || $fw->{currentFirmware} // '';
    my $fill_num  = exists $fill_map{$fill_t} ? $fill_map{$fill_t} : -1;
    my $wifi_num  = exists $wifi_map{$wifi_t} ? $wifi_map{$wifi_t} : -1;

    # -- UDP to Miniserver -----------------------------------------------------
    # UDP state: fields match VirtualInUdpCmd entries in the VIU template
    # Analog=true fields MUST send clean integers/numbers (no trailing whitespace/text)
    # Analog=false fields send text strings (captured up to newline by Loxone )
    my %state = (
        on        => ($fanc eq '1') ? 1 : 0,         # Analog=true  integer 0/1
        intensity => int($speedc || 0),               # Analog=true  integer 1-3
        fill      => int($fill_num || 0),             # Analog=true  integer 0-100
        wifi      => int($wifi_num || 0),             # Analog=true  integer 0-100
        squarem   => int($squarem || 0),              # Analog=true  integer
        online    => ($online ? 1 : 0),               # Analog=true  integer 0/1
        fill_text => $fill_t   || '',                 # Analog=false text
        perfume   => $perfume_t || '',                # Analog=false text
        battery   => $batt_t   || '',                 # Analog=false text
        version   => do { (my $v = $version || '0') =~ s/\.//g; int($v) }, # Analog=true integer e.g. 5.4->54
        room      => $room_name || '',                # Analog=false text
        roomtype  => $roomtype  || '',                # Analog=false text
    );

    if ($enable_udp && $ms_ip) {
        send_udp($hub_key, \%state, $ms_ip, $ms_port);
        LOGINF("Sent UDP for '$room_name': on=$state{on} intensity=$state{intensity} fill=$state{fill}");
    } elsif ($enable_udp && !$ms_ip) {
        LOGWARN("UDP enabled but no Miniserver IP - skipping UDP for '$room_name'");
    } else {
    }

    # -- Accumulate for cache update -------------------------------------------
    push @cache_hubs, {
        name            => $room_name,
        hash            => $hash,
        hublot          => $hublot,
        status          => $online,
        on              => ($fanc eq '1') ? 1 : 0,
        intensity       => int($speedc),
        squarem         => $squarem,
        roomtype        => $roomtype,
        roomc           => $roomc,
        led             => ($ledc eq '1') ? 1 : 0,
        fan_state       => $fan_state,
        next_fan_change => $next_change,
        fill            => $fill_num,
        fill_text       => $fill_t || '?',
        perfume         => $perfume_t,
        battery         => $batt_t,
        wifi            => $wifi_num,
        wifi_desc       => $wifi_desc,
        online          => $online,
        version         => $version,
    };
}

# -- Update hubs_cache.json so web UI shows live data --------------------------
if (@cache_hubs) {
    save_json(CACHE_FILE, \@cache_hubs);
    LOGINF("Updated hubs_cache.json with " . scalar(@cache_hubs) . " hub(s).");
}

LOGEND;
exit 0;

# -- UDP sender -----------------------------------------------------------------
sub send_udp {
    my ($hub_key, $state, $ip, $port) = @_;
    my $sock = IO::Socket::INET->new(
        PeerAddr => $ip, PeerPort => $port, Proto => 'udp',
    ) or do { LOGERR("UDP socket error: $!"); return; };
    for my $field (sort keys %$state) {
        $sock->send("rituals/${hub_key}/${field}=$state->{$field}\n");
    }
    $sock->close();
}

# -- Helpers --------------------------------------------------------------------
sub read_token {
    return undef unless -f TOKEN_FILE;
    open(my $fh, '<', TOKEN_FILE) or return undef;
    local $/; my $raw = <$fh>; close $fh;
    my $d = eval { decode_json($raw) } // {};
    my $t = $d->{eva_token}  // '';
    my $e = $d->{expires_at} // 0;
    LOGWARN("Token expired at " . localtime($e)) if $e && $e < time();
    return $t || undef;
}

sub load_json {
    my ($f) = @_;
    return {} unless -f $f;
    open(my $fh, '<:encoding(UTF-8)', $f) or do { LOGERR("Cannot read $f: $!"); return {}; };
    local $/; my $raw = <$fh>; close $fh;
    return eval { decode_json($raw) } // {};
}

sub save_json {
    my ($f, $d) = @_;
    my $tmp = "$f.tmp";
    open(my $fh, '>:encoding(UTF-8)', $tmp)
        or do { LOGERR("Cannot write $tmp: $!"); return; };
    print $fh encode_json($d);
    close $fh;
    rename($tmp, $f) or LOGERR("Rename failed: $!");
}

sub sanitize {
    my ($s) = @_;
    $s = lc $s; $s =~ s/[^a-z0-9]+/_/g; $s =~ s/^_|_$//g;
    return $s || 'genie';
}
