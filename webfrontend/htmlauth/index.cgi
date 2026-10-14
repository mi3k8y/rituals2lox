#!/usr/bin/perl
# Rituals2Lox  -  Web Interface
# Pages: config (default), hubs, wizard, logs

use strict;
use warnings;
use utf8;
use Encode qw(decode encode);
use CGI;
use JSON;
use LoxBerry::System;
use LoxBerry::Web;
use LoxBerry::Log;
use HTML::Template;
use LWP::UserAgent;
use HTTP::Request;

# Ensure UTF-8 output (needed for Czech/accented room names)
binmode(STDOUT, ':encoding(UTF-8)');

my $plugin  = LoxBerry::System::plugindata();
my $version = $plugin->{PLUGINDB_VERSION} // '0.1.0';

my $creds_file = "$lbpdatadir/credentials.json";
my $token_file = "$lbpdatadir/token.json";
my $cfg_file   = "$lbpdatadir/config.json";
my $hubs_file  = "$lbpdatadir/hubs_cache.json";

my $log = LoxBerry::Log->new( name => 'webui', addtime => 1 );

my $cgi    = CGI->new;
my $page   = $cgi->param('page')   // 'config';
my $action = $cgi->param('action') // '';

my $template = HTML::Template->new(
    filename          => "$lbptemplatedir/index.html",
    global_vars       => 1,
    loop_context_vars => 1,
    die_on_bad_params => 0,
);

my %L = LoxBerry::Web::readlanguage($template, "language.ini");

# -- Actions --------------------------------------------------------------------

if ($action eq 'save') {
    my $email    = $cgi->param('email')              // '';
    my $password = $cgi->param('password')            // '';
    my $ms_ip    = $cgi->param('miniserver_ip')       // '';
    my $ms_port  = int($cgi->param('miniserver_port') // 56069);

    my $old = load_json($creds_file);
    save_json($creds_file, {
        email    => $email    || $old->{email}    || '',
        password => $password || $old->{password} || '',
    });
    chmod 0600, $creds_file;
    my $enable_udp  = (($cgi->param('enable_udp')  // '0') eq '1') ? 1 : 0;
    my $enable_http = (($cgi->param('enable_http') // '1') eq '1') ? 1 : 0;
    save_json($cfg_file, { miniserver_ip => $ms_ip, miniserver_port => $ms_port, enable_udp => $enable_udp, enable_http => $enable_http });
    LOGINF("Configuration saved.");
    $template->param( SAVE_OK => 1 );

} elsif ($action eq 'refresh_token') {
    LOGINF("Manual token refresh triggered.");
    my $rc = system('perl', "$lbpbindir/token-manager.pl", 'refresh');
    if ($rc == 0) {
        $template->param( REFRESH_OK => 1 );
        LOGINF("Token refresh succeeded.");
    } else {
        $template->param( REFRESH_ERROR => 1 );
        LOGWARN("Token refresh failed (exit=" . ($rc >> 8) . ").");
    }

} elsif ($action eq 'run_grabber') {
    LOGINF("Manual grabber run triggered.");
    my $rc = system('perl', "$lbpbindir/grabber.pl");
    if ($rc == 0) {
        $template->param( SAVE_OK => 1 );
        LOGINF("Grabber run succeeded.");
    } else {
        LOGWARN("Grabber run failed (exit=" . ($rc >> 8) . ").");
    }
    $page = 'hubs';

} elsif ($action eq 'scan_hubs') {
    my $result = scan_hubs_live();
    if ($result->{ok}) {
        $template->param( SCAN_OK => 1, SCAN_COUNT => scalar @{$result->{hubs}} );
        save_json($hubs_file, $result->{hubs});
    } else {
        $template->param( SCAN_ERROR => 1, SCAN_MSG => $result->{error} );
    }
    $page = 'hubs';

} elsif ($action eq 'dump_raw') {
    my $raw = fetch_raw_hubs();
    $template->param( RAW_DUMP => $raw );
    $page = 'logs';

} elsif ($action eq 'dump_sensors') {
    my $hub_hash = $cgi->param('hub_hash') // '';
    my $raw = fetch_raw_sensors($hub_hash);
    $template->param( RAW_DUMP => "Sensors for hub $hub_hash:

$raw" );
    $page = 'logs';

} elsif ($action eq 'dump_attributes') {
    my $hub_hash = $cgi->param('hub_hash') // '';
    my $raw = fetch_raw_attributes($hub_hash);
    $template->param( RAW_DUMP => "Attributes for hub $hub_hash:

$raw" );
    $page = 'logs';

} elsif ($action eq 'download_viu' || $action eq 'download_vo' || $action eq 'download_vi') {
    # handled below after variables are declared
}

# -- Navigation -----------------------------------------------------------------

my $lb_host = LoxBerry::System::lbhostname() // 'loxberry';
my $sendcmd_base = "http://$lb_host/plugins/rituals2lox/sendcmd.cgi";

$template->param(
    PLUGIN_VERSION => $version,
    PAGE_CONFIG    => ($page eq 'config') ? 1 : 0,
    PAGE_HUBS      => ($page eq 'hubs')   ? 1 : 0,
    PAGE_WIZARD    => ($page eq 'wizard') ? 1 : 0,
    PAGE_LOGS      => ($page eq 'logs')   ? 1 : 0,
    SENDCMD_BASE   => $sendcmd_base,
);

# -- Config page params ---------------------------------------------------------

my %tok = get_token_status();
foreach my $key (keys %tok) { $template->param( $key => $tok{$key} ); }

my $cfg   = load_json($cfg_file);
my $creds = load_json($creds_file);

# Auto-detect Miniserver from LoxBerry system config
my $auto_ms_ip   = '';
my $auto_ms_port = 56069;
my %ms_list = LoxBerry::System::get_miniservers();
if (%ms_list && $ms_list{1}) {
    $auto_ms_ip   = $ms_list{1}{IPAddress} // '';
    $auto_ms_port = $ms_list{1}{Port}      // 56069;
}

# Plugin config overrides auto-detection
my $ms_ip   = $cfg->{miniserver_ip}   || $auto_ms_ip;
my $ms_port = $cfg->{miniserver_port} || $auto_ms_port;

$template->param(
    EMAIL           => $creds->{email} // '',
    MINISERVER_IP   => $ms_ip,
    MINISERVER_PORT => $ms_port,
    UDP_PORT        => $ms_port,
    MS_AUTODETECTED => ($auto_ms_ip && !$cfg->{miniserver_ip}) ? 1 : 0,
    MS_AUTO_IP      => $auto_ms_ip,
    ENABLE_UDP      => $cfg->{enable_udp}  // 0,
    ENABLE_HTTP     => (exists $cfg->{enable_http}) ? $cfg->{enable_http} : 1,
);

# -- Hubs page params -----------------------------------------------------------

# hubs_cache is stored as a JSON array; load_json returns {} for missing files
# so we need special handling
my $hubs_cache = [];
if (-f $hubs_file) {
    my $raw_cache = load_json($hubs_file);
    $hubs_cache = $raw_cache if ref $raw_cache eq 'ARRAY';
}
if (ref $hubs_cache eq 'ARRAY' && @$hubs_cache) {
    my @hub_rows;
    for my $h (@$hubs_cache) {
        my $hub_key = sanitize($h->{name} // 'genie');
        my $h_hash  = $h->{hash} // '';

        # Intensity: numeric to label
        my $int_num = $h->{intensity} // 0;
        my $int_label = $int_num == 1 ? 'Low'
                      : $int_num == 2 ? 'Medium'
                      : $int_num == 3 ? 'High'
                      : $int_num == 0 ? 'Off'
                      : $int_num;

        # Room size label
        my $roomc_map = { '1'=>'Small','2'=>'Medium','3'=>'Large','4'=>'Extra Large' };
        my $roomc_label = $roomc_map->{ $h->{roomc} // '' } // '';

        # Schedule info
        my $next_change = $h->{next_fan_change} // '';
        my $current_state = $h->{fan_state} // '';

        # UDP key prefix for Loxone reference
        my $udp_prefix = "rituals/$hub_key/";

        push @hub_rows, {
            HUB_NAME        => $h->{name}       // 'Unknown',
            HUB_HUBLOT      => $h->{hublot}     // '',
            HUB_HASH        => $h_hash,
            HUB_KEY         => $hub_key,
            HUB_ON          => $h->{on}         // 0,
            HUB_ON_TEXT     => ($h->{on} // 0) ? 'ON' : 'OFF',
            HUB_INTENSITY   => $int_num,
            HUB_INT_LABEL   => $int_label,
            HUB_FILL        => $h->{fill}       // -1,
            HUB_FILL_TEXT   => $h->{fill_text}  // '?',
            HUB_PERFUME     => $h->{perfume}    // '',
            HUB_BATTERY     => $h->{battery}    // '',
            HUB_ONLINE      => $h->{online}     // 0,
            HUB_WIFI        => $h->{wifi}       // -1,
            HUB_WIFI_DESC   => $h->{wifi_desc}  // '',
            HUB_VERSION     => $h->{version}    // '',
            HUB_SQUAREM     => $h->{squarem}    // '',
            HUB_ROOMTYPE    => $h->{roomtype}   // '',
            HUB_ROOMC       => $h->{roomc}      // '',
            HUB_ROOMC_LABEL => $roomc_label,
            HUB_LED         => ($h->{led} // 0) ? 'On' : 'Off',
            HUB_FAN_STATE   => $h->{fan_state}  // '',
            HUB_NEXT_CHANGE => $h->{next_fan_change} // '',
            HUB_UDP_PREFIX  => $udp_prefix,
            CMD_ON1         => "$sendcmd_base?command=on&hub=$h_hash&intensity=1",
            CMD_ON2         => "$sendcmd_base?command=on&hub=$h_hash&intensity=2",
            CMD_ON3         => "$sendcmd_base?command=on&hub=$h_hash&intensity=3",
            CMD_OFF         => "$sendcmd_base?command=off&hub=$h_hash",
        };
    }
    $template->param( HUBS => \@hub_rows, HAS_HUBS => 1 );
} else {
    $template->param( HAS_HUBS => 0 );
}

# Pass UDP config to template (for conditional buttons)
$template->param(
    ENABLE_UDP      => $cfg->{enable_udp}  // 0,
    ENABLE_HTTP     => (exists $cfg->{enable_http}) ? $cfg->{enable_http} : 1,
    MINISERVER_IP   => $ms_ip   // '',
    MINISERVER_PORT => $ms_port // 56069,
);

# -- Wizard page params ---------------------------------------------------------
# -- Download XML files --------------------------------------------------------
# Generates one VirtualInUdp or VirtualOut XML per hub
# VirtualInUdp/VirtualOut IS the root element  -  no IoData wrapper
# (matches MiRobot2Lox-NG templatebuilder approach)
if ($action eq 'download_viu' || $action eq 'download_vo' || $action eq 'download_vi') {
    # vi = HTTP Virtual Input (Loxone polls state.cgi)
    # viu = UDP Virtual Input (LoxBerry pushes via cron)
    # vo  = Virtual Output (HTTP commands)
    my $type = ($action eq 'download_vo') ? 'vo'
             : ($action eq 'download_viu') ? 'viu_udp'
             : 'vi';   # download_vi or default
    my $hub_idx  = int($cgi->param('hub_idx') // 0);
    my $ms_port  = $cfg->{miniserver_port} // 56069;

    # Get the specific hub (one file per hub, like MiRobot does per robot)
    my $h = (ref $hubs_cache eq 'ARRAY' && @$hubs_cache)
        ? $hubs_cache->[$hub_idx] : undef;

    unless ($h) {
        print "Content-Type: text/plain\n\n";
        print "No hub data. Please scan for Genies first.";
        exit;
    }

    my $hub_key  = sanitize($h->{name} // 'genie');
    my $hub_name = $h->{name} // $hub_key;
    my $hub_hash = $h->{hash}   // '';
    my $hub_lot  = $h->{hublot} // '';
    my $safe_name = $hub_name;
    $safe_name =~ s/[^a-zA-Z0-9_-]/_/g;

    my $filename = ($type eq 'vo')      ? "VO_Rituals_${safe_name}.xml"
              : ($type eq 'viu_udp') ? "VIU_Rituals_${safe_name}.xml"
              :                        "VI_Rituals_${safe_name}.xml";

    # BOM required by Loxone Config
    my $bom = chr(0xEF) . chr(0xBB) . chr(0xBF);
    my $xml = $bom . "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n";

    if ($type eq 'vi') {
        # VirtualInHttp  -  Loxone polls each field URL every Cycle seconds
        # Much more reliable than UDP: Loxone controls poll rate, no firewall issues
        my $lb_host = LoxBerry::System::lbhostname() // 'loxberry';
        my $state_url = "http://$lb_host/plugins/rituals2lox/state.cgi?hub=$hub_hash&field=";
        $xml .= "<VirtualInHttp Title=\"Rituals $hub_name\"";
        $xml .= " Comment=\"Rituals Genie $hub_lot\"";
        $xml .= " Address=\"http://$lb_host/plugins/rituals2lox/state.cgi\"";
        $xml .= " Cycle=\"60\">\n";
        for my $f (
            [on        => 'Power (0=off 1=on)',            'false'],
            [intensity => 'Intensity (1=low 2=med 3=high)', 'true'],
            [fill      => 'Cartridge fill %',              'true'],
            [perfume   => 'Perfume name',                  'false'],
            [wifi      => 'WiFi signal %',                 'true'],
            [battery   => 'Battery',                       'false'],
            [online    => 'Online (0/1)',                   'false'],
            [version   => 'Firmware',                      'false'],
            [room      => 'Room name',                     'false'],
        ) {
            my ($field, $desc, $analog) = @$f;
            $xml .= "  <VirtualInHttpCmd Title=\"$hub_name $field\"";
            $xml .= " Comment=\"$desc\"";
            $xml .= " Check=\"${state_url}${field}\\v\"";
            $xml .= " Analog=\"$analog\"/>\n";
        }
        $xml .= "</VirtualInHttp>\n";
    } elsif ($type eq 'viu_udp') {
        # UDP Virtual Input  -  LoxBerry pushes data to Miniserver via cron
        my $lb_host = LoxBerry::System::lbhostname() // 'loxberry';
        $xml .= "<VirtualInUdp Title=\"Rituals $hub_name\"";
        $xml .= " Comment=\"Rituals Genie $hub_lot\"";
        $xml .= " Address=\"$lb_host\" UdpPort=\"$ms_port\">\n";
        for my $f (
            [on        => 'Power (0=off 1=on)',              'true'],
            [intensity => 'Intensity (1=low 2=med 3=high)',   'true'],
            [fill      => 'Cartridge fill %',                 'true'],
            [fill_text => 'Cartridge fill text',              'false'],
            [perfume   => 'Perfume name',                     'false'],
            [wifi      => 'WiFi signal strength %',           'true'],
            [battery   => 'Battery level',                    'false'],
            [online    => 'Online status (0=off 1=on)',        'true'],
            [version   => 'Firmware version (e.g. 54 = v5.4)',  'true'],
            [room      => 'Room name',                        'false'],
            [squarem   => 'Room size in m2',                  'true'],
            [roomtype  => 'Room type',                        'false'],
        ) {
            my ($field, $desc, $analog) = @$f;
            $xml .= "  <VirtualInUdpCmd Title=\"$hub_name $field\"";
            $xml .= " Comment=\"$desc\"";
            $xml .= " CmdIdentify=\"rituals/${hub_key}/${field}=\\v\"";
            $xml .= " Analog=\"$analog\"/>\n";
        }
        $xml .= "</VirtualInUdp>\n";

    } else {
        # VirtualOut IS the root element (no IoData wrapper)
        my $lb_host = LoxBerry::System::lbhostname() // 'loxberry';
        my $lb_port = LoxBerry::System::lbwebserverport() // 80;
        my $lb_base = ($lb_port == 80) ? "http://$lb_host" : "http://$lb_host:$lb_port";
        my $cmd_path = "/plugins/rituals2lox/sendcmd.cgi";
        $xml .= "<VirtualOut Title=\"Rituals $hub_name\"";
        $xml .= " Comment=\"Rituals Genie $hub_lot\"";
        $xml .= " Address=\"$lb_base\"";
        $xml .= " CmdInit=\"\" CloseAfterSend=\"true\" CmdSep=\"\">\n";
        for my $c (
            ["Turn On Low",    "${cmd_path}?command=on&amp;hub=$hub_hash&amp;intensity=1"],
            ["Turn On Medium", "${cmd_path}?command=on&amp;hub=$hub_hash&amp;intensity=2"],
            ["Turn On High",   "${cmd_path}?command=on&amp;hub=$hub_hash&amp;intensity=3"],
            ["Turn Off",       "${cmd_path}?command=off&amp;hub=$hub_hash"],
            ["Intensity Low",  "${cmd_path}?command=intensity&amp;hub=$hub_hash&amp;value=1"],
            ["Intensity Med",  "${cmd_path}?command=intensity&amp;hub=$hub_hash&amp;value=2"],
            ["Intensity High", "${cmd_path}?command=intensity&amp;hub=$hub_hash&amp;value=3"],
        ) {
            $xml .= "  <VirtualOutCmd Title=\"$hub_name $c->[0]\" Comment=\"\"";
            $xml .= " CmdOnMethod=\"GET\" CmdOffMethod=\"GET\"";
            $xml .= " CmdOn=\"$c->[1]\" CmdOnHTTP=\"\" CmdOnPost=\"\"";
            $xml .= " CmdOff=\"\" CmdOffHTTP=\"\" CmdOffPost=\"\"";
            $xml .= " Analog=\"false\" Repeat=\"0\" RepeatRate=\"0\"/>\n";
        }
        $xml .= "</VirtualOut>\n";
    }

    binmode(STDOUT, ':raw');
    print "Content-Type: application/octet-stream\n";
    print "Content-Disposition: attachment; filename=\"$filename\"\n";
    print "\n";
    print $xml;
    exit;
}


if (ref $hubs_cache eq 'ARRAY' && @$hubs_cache) {
    my $ms_port = $cfg->{miniserver_port} // 56069;

    # Build VIU/VO XML in correct Loxone IoData format
    my $xml_hdr   = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<IoData>\n";
    my $viu_xml     = $xml_hdr;   # HTTP Virtual Input (Loxone polls state.cgi)
    my $viu_udp_xml = $xml_hdr;   # UDP Virtual Input (LoxBerry pushes)
    my $vo_xml      = $xml_hdr;   # Virtual Output (HTTP commands)

    my @wizard_hubs;

    for my $h (@$hubs_cache) {
        my $hub_key  = sanitize($h->{name} // 'genie');
        my $hub_name = $h->{name}   // $hub_key;
        my $hub_hash = $h->{hash}   // '';
        my $hub_lot  = $h->{hublot} // '';

        push @wizard_hubs, {
            WIZ_NAME   => $hub_name,
            WIZ_HUBLOT => $hub_lot,
            WIZ_KEY    => $hub_key,
            WIZ_IDX    => scalar(@wizard_hubs),
        };

        # -- VIU: HTTP input per Genie  -  Loxone polls state.cgi for each field --
        my $lb_host_viu = LoxBerry::System::lbhostname() // 'loxberry';
        my $lb_port_viu = LoxBerry::System::lbwebserverport() // 80;
        my $lb_base_viu = ($lb_port_viu == 80) ? "http://$lb_host_viu" : "http://$lb_host_viu:$lb_port_viu";
        my $state_url_wiz = "$lb_base_viu/plugins/rituals2lox/state.cgi?hub=$hub_hash&field=";
        $viu_xml .= "  <VirtualInHttp Title=\"Rituals $hub_name\" Comment=\"Rituals Genie $hub_lot\"";
        $viu_xml .= " Address=\"$lb_base_viu/plugins/rituals2lox/state.cgi\" Cycle=\"60\">\n";
        for my $f (
            [on        => 'Power (0=off 1=on)',             'false'],
            [intensity => 'Intensity (1=low 2=med 3=high)',  'true'],
            [fill      => 'Cartridge fill %',               'true'],
            [perfume   => 'Perfume name',                   'false'],
            [wifi      => 'WiFi signal %',                  'true'],
            [battery   => 'Battery',                        'false'],
            [online    => 'Online (0/1)',                    'false'],
            [version   => 'Firmware',                       'false'],
            [room      => 'Room name',                      'false'],
        ) {
            my ($field, $desc, $analog) = @$f;
            $viu_xml .= "    <VirtualInHttpCmd Title=\"$hub_name $field\" Comment=\"$desc\"";
            $viu_xml .= " Check=\"${state_url_wiz}${field}\\v\" Analog=\"$analog\"/>\n";
        }
        $viu_xml .= "  </VirtualInHttp>\n";

        # -- VIU UDP: UDP push from LoxBerry to Miniserver ------------------
        $viu_udp_xml .= "  <VirtualInUdp Title=\"Rituals $hub_name\"";
        $viu_udp_xml .= " Comment=\"Rituals Genie $hub_lot\"";
        $viu_udp_xml .= " Address=\"$lb_host_viu\" UdpPort=\"$ms_port\">\n";
        for my $f (
            [on        => 'Power (0=off 1=on)',              'true'],
            [intensity => 'Intensity (1=low 2=med 3=high)',   'true'],
            [fill      => 'Cartridge fill %',                 'true'],
            [fill_text => 'Cartridge fill text',              'false'],
            [perfume   => 'Perfume name',                     'false'],
            [wifi      => 'WiFi signal strength %',           'true'],
            [battery   => 'Battery level',                    'false'],
            [online    => 'Online status (0=off 1=on)',        'true'],
            [version   => 'Firmware version (e.g. 54 = v5.4)',  'true'],
            [room      => 'Room name',                        'false'],
            [squarem   => 'Room size in m2',                  'true'],
            [roomtype  => 'Room type',                        'false'],
        ) {
            my ($field, $desc, $analog) = @$f;
            $viu_udp_xml .= "    <VirtualInUdpCmd Title=\"$hub_name $field\"";
            $viu_udp_xml .= " Comment=\"$desc\"";
            $viu_udp_xml .= " CmdIdentify=\"rituals/${hub_key}/${field}=\\v\"";
            $viu_udp_xml .= " Analog=\"$analog\"/>\n";
        }
        $viu_udp_xml .= "  </VirtualInUdp>\n";

        # -- VO: one HTTP output device per Genie, one cmd per action --------
        my $lb_host_wiz = LoxBerry::System::lbhostname() // 'loxberry';
        my $lb_port_wiz = LoxBerry::System::lbwebserverport() // 80;
        my $lb_base_wiz = ($lb_port_wiz == 80) ? "http://$lb_host_wiz" : "http://$lb_host_wiz:$lb_port_wiz";
        my $cmd_path_wiz = "/plugins/rituals2lox/sendcmd.cgi";
        $vo_xml .= "  <VirtualOut Title=\"Rituals $hub_name\" Comment=\"Rituals Genie $hub_lot\"";
        $vo_xml .= " Address=\"$lb_base_wiz\" CmdInit=\"\" CloseAfterSend=\"true\" CmdSep=\"\">\n";
        for my $c (
            ["Turn On Low",    "${cmd_path_wiz}?command=on&amp;hub=$hub_hash&amp;intensity=1"],
            ["Turn On Medium", "${cmd_path_wiz}?command=on&amp;hub=$hub_hash&amp;intensity=2"],
            ["Turn On High",   "${cmd_path_wiz}?command=on&amp;hub=$hub_hash&amp;intensity=3"],
            ["Turn Off",       "${cmd_path_wiz}?command=off&amp;hub=$hub_hash"],
            ["Intensity Low",  "${cmd_path_wiz}?command=intensity&amp;hub=$hub_hash&amp;value=1"],
            ["Intensity Med",  "${cmd_path_wiz}?command=intensity&amp;hub=$hub_hash&amp;value=2"],
            ["Intensity High", "${cmd_path_wiz}?command=intensity&amp;hub=$hub_hash&amp;value=3"],
        ) {
            $vo_xml .= "    <VirtualOutCmd Title=\"$hub_name $c->[0]\" Comment=\"\"";
            $vo_xml .= " CmdOnMethod=\"GET\" CmdOffMethod=\"GET\"";
            $vo_xml .= " CmdOn=\"$c->[1]\" CmdOnHTTP=\"\" CmdOnPost=\"\"";
            $vo_xml .= " CmdOff=\"\" CmdOffHTTP=\"\" CmdOffPost=\"\"";
            $vo_xml .= " Analog=\"false\" Repeat=\"0\" RepeatRate=\"0\"/>\n";
        }
        $vo_xml .= "  </VirtualOut>\n";
    }

    $viu_xml     .= "</IoData>\n";
    $viu_udp_xml .= "</IoData>\n";
    $vo_xml      .= "</IoData>\n";

    $template->param(
        WIZARD_UDP_PORT    => $ms_port,
        WIZARD_MINISERVER  => "$ms_ip:$ms_port",
        WIZARD_VIU_XML     => $viu_xml,
        WIZARD_VIU_UDP_XML => $viu_udp_xml,
        WIZARD_VO_XML      => $vo_xml,
        WIZARD_HAS_DATA    => 1,
        WIZARD_HUBS        => \@wizard_hubs,
    );
}


# -- Logs page ------------------------------------------------------------------

if ($page eq 'logs') {
    $template->param( LOGLIST => LoxBerry::Web::loglist_html( package => 'rituals2lox' ) );
}

# -- Render ---------------------------------------------------------------------

LoxBerry::Web::lbheader("Rituals2Lox V$version", '', 'help.html');
print $template->output();
LoxBerry::Web::lbfooter();
exit;

# -- Hub scanner ----------------------------------------------------------------
# V2 API response structure (confirmed from raw response):
#   Array of hub objects directly (Shape B  -  no nested 'hub' key)
#   Each hub has:
#     .hublot           -  lot ID (e.g. LOT124-39-E09D1-18467)
#     .hash             -  64-char hex identifier for API calls
#     .status           -  1=online 0=offline
#     .attributeValues  -  hash of actual live values:
#                          fanc: "0"/"1" (off/on)
#                          speedc: "1"/"2"/"3" (intensity)
#                          roomnamec: "J?delna" (room name string)
#                          roomc: room size index
#                          squaremeterc: room size m?
#                          ledc: "0"/"1"
#     .attributes       -  capability flags only (booleans), NOT values
#     .sensors          -  capability flags only (booleans), NOT values
#   Sensor detail values (fill, perfume, wifi, firmware) require a separate
#   GET /apiv2/hubs/{hash}/attributes call per device.

sub scan_hubs_live {
    unless (-f $token_file) {
        return { ok => 0, error => 'No token  -  authenticate first.' };
    }
    my $td    = load_json($token_file);
    my $token = $td->{eva_token} // '';
    return { ok => 0, error => 'Token missing in token.json.' } unless $token;

    my $ua = LWP::UserAgent->new( agent => 'Rituals2Lox/0.1', timeout => 20 );

    # Step 1: Get hub list
    my $req = HTTP::Request->new( GET => 'https://rituals.sense-company.com/apiv2/account/hubs' );
    $req->header( Authorization => $token );
    my $resp = $ua->request($req);

    unless ($resp->is_success) {
        LOGERR("Hub list HTTP error: " . $resp->status_line);
        return { ok => 0, error => 'API error: ' . $resp->status_line };
    }

    my $data = eval { decode_json($resp->decoded_content) };
    if ($@) {
        LOGERR("JSON parse error on hub list: $@");
        return { ok => 0, error => "JSON parse error: $@" };
    }

    unless (ref $data eq 'ARRAY') {
        LOGERR("Hub list is not an array: " . ref($data));
        return { ok => 0, error => 'Unexpected response  -  not an array.' };
    }

    LOGINF("Hub list: " . scalar(@$data) . " device(s) found.");

    my @hubs;
    for my $entry (@$data) {
        # Each entry IS the hub object directly (hub key is null)
        my $hash   = $entry->{hash}   // '';
        my $hublot = $entry->{hublot} // '';
        my $status = $entry->{status} // 0;   # 1=online, 0=offline

        # attributeValues contains the actual live device state
        my $av = $entry->{attributeValues} // {};
        my $fanc      = $av->{fanc}      // '0';
        my $speedc    = $av->{speedc}    // '0';
        my $roomnamec = $av->{roomnamec} // $av->{fspacenamec} // $hublot;
        my $squarem   = $av->{squaremeterc} // '';
        my $roomtype  = $av->{fspacetypec}  // '';
        my $ledc      = $av->{ledc}      // '0';

        LOGINF("Hub: hublot=$hublot name='$roomnamec' fanc=$fanc speedc=$speedc status=$status");

        # Step 2: Fetch per-hub sensor values
        # version_t fetched from /sensors/versionc; fallback to firmwareInfo
        my $fw_fallback = ($entry->{firmwareInfo} // {})->{currentFirmware} // '';

        my ($fill_t, $perfume_t, $wifi_t, $batt_t, $version_t) = ('', '', '', '', '');
        my $wifi_desc = '';
        if ($hash) {
            # Sensors use: GET /apiv2/hubs/{hash}/sensors/{name}
            # Response format: {"description":"...","value":"..."}
            # The "value" field contains the actual reading (title/label string).
            # Only fetch sensors flagged as true in $entry->{sensors}.
            my $sensors_cap = $entry->{sensors} // {};

            my %sensor_targets = (
                fillc    => \$fill_t,
                rfidc    => \$perfume_t,
                wific    => \$wifi_t,
                battc    => \$batt_t,
                versionc => \$version_t,
            );

            for my $name (keys %sensor_targets) {
                next unless $sensors_cap->{$name};  # skip if sensor not present on device

                my $url  = "https://rituals.sense-company.com/apiv2/hubs/$hash/sensors/$name";
                my $sreq = HTTP::Request->new( GET => $url );
                $sreq->header( Authorization => $token );
                my $sresp = $ua->request($sreq);

                if ($sresp->is_success) {
                    my $d = eval { decode_json($sresp->decoded_content) };
                    if (!$@ && ref $d eq 'HASH') {
                        my $val  = $d->{value} // $d->{title} // '';
                        my $desc = $d->{description} // '';
                        ${ $sensor_targets{$name} } = $val;
                        # wific description often contains the dBm value
                        $wifi_desc = $desc if $name eq 'wific' && $desc;
                        LOGINF("  sensor $name = '$val' desc='$desc'");
                    }
                } else {
                    LOGWARN("Sensor $name HTTP " . $sresp->code . " for $hublot");
                }
            }

            # Note: device local IP not available via V2 cloud API
        }

        LOGINF("  fill='$fill_t' perfume='$perfume_t' wifi='$wifi_t' version='$version_t'");

        # Rituals fill level titles (confirmed from real API responses)
        # "No measurement available" = sensor present but no reading yet
        my %fill_map = (
            'Full'                     => 100,
            'Half'                     => 50,
            'Low'                      => 25,
            'Empty'                    => 0,
            'No measurement available' => -1,  # sensor exists but no data
        );
        my %wifi_map = (
            'High'   => 100,
            'Medium' => 50,
            'Low'    => 25,
        );

        # For fill display: if -1 show "?" not "-1%"
        my $fill_num  = exists $fill_map{$fill_t}  ? $fill_map{$fill_t}  : -1;
        my $wifi_num  = exists $wifi_map{$wifi_t}  ? $wifi_map{$wifi_t}  : -1;
        my $fill_disp = $fill_t || '?';

        # nextFanChange schedule info
        my $nfc           = $entry->{nextFanChange} // {};
        my $fan_state     = $nfc->{currentState}        // '';
        my $next_time     = $nfc->{nextStateChangeTime}  // '';
        my $next_val      = $nfc->{nextStateChangeValue};
        my $next_change   = '';
        if ($next_time && defined $next_val) {
            $next_change = "$next_time (speed: $next_val)";
        } elsif ($fan_state) {
            $next_change = $fan_state;
        }

        push @hubs, {
            name            => $roomnamec,
            hash            => $hash,
            hublot          => $hublot,
            status          => $status,
            on              => ($fanc eq '1') ? 1 : 0,
            intensity       => int($speedc // 0),
            squarem         => $squarem,
            roomtype        => $roomtype,
            roomc           => $av->{roomc} // '',
            led             => ($ledc eq '1') ? 1 : 0,
            fan_state       => $fan_state,
            next_fan_change => $next_change,
            fill            => $fill_num,
            fill_text       => $fill_disp,
            perfume         => $perfume_t,
            battery         => $batt_t,
            wifi            => $wifi_num,
            online          => $status ? 1 : 0,
            version         => $version_t || $fw_fallback,
            wifi_desc       => $wifi_desc,

        };
    }

    LOGINF("Scan complete  -  " . scalar(@hubs) . " hub(s) parsed.");
    return { ok => 1, hubs => \@hubs };
}

# Fetch raw hub JSON for debug dumping
sub fetch_raw_hubs {
    return '{"error":"No token file"}' unless -f $token_file;
    my $td    = load_json($token_file);
    my $token = $td->{eva_token} // '';
    return '{"error":"No eva_token in token.json"}' unless $token;

    my $ua = LWP::UserAgent->new( agent => 'Rituals2Lox/0.1', timeout => 15 );
    my $req = HTTP::Request->new( GET => 'https://rituals.sense-company.com/apiv2/account/hubs' );
    $req->header( Authorization => $token );
    my $resp = $ua->request($req);
    return '{"error":"HTTP ' . $resp->status_line . '"}' unless $resp->is_success;
    return $resp->decoded_content;
}

# -- Helpers --------------------------------------------------------------------

# Extract a scalar value from a sensor field regardless of whether it's
# a plain scalar, a hash with 'title', or a hash with 'value'
sub _sensor_val {
    my ($v) = @_;
    return '' unless defined $v;
    return $v->{title} // $v->{value} // '' if ref $v eq 'HASH';
    return '' if ref $v;   # array or other ref  -  skip
    return "$v";           # plain scalar  -  stringify (handles booleans/numbers)
}

# Fetch raw hub JSON for debug dumping
sub fetch_raw_hubs {
    return '{"error":"No token file"}' unless -f $token_file;
    my $td    = load_json($token_file);
    my $token = $td->{eva_token} // '';
    return '{"error":"No eva_token in token.json"}' unless $token;

    my $ua = LWP::UserAgent->new( agent => 'Rituals2Lox/0.1', timeout => 15 );
    my $req = HTTP::Request->new( GET => 'https://rituals.sense-company.com/apiv2/account/hubs' );
    $req->header( Authorization => $token );
    my $resp = $ua->request($req);
    return '{"error":"HTTP ' . $resp->status_line . '"}' unless $resp->is_success;
    return $resp->decoded_content;
}

sub fetch_raw_sensors {
    my ($hub_hash) = @_;
    return '{"error":"No hub hash provided"}' unless $hub_hash;
    return '{"error":"No token file"}' unless -f $token_file;
    my $td    = load_json($token_file);
    my $token = $td->{eva_token} // '';
    return '{"error":"No eva_token"}' unless $token;

    my $ua = LWP::UserAgent->new( agent => 'Rituals2Lox/0.1', timeout => 15 );
    my $out = "Testing all known Rituals API endpoints for hub: $hub_hash
";
    $out .= "=" x 60 . "

";

    # Comprehensive test of all plausible URL patterns
    my @paths = (
        # Working attribute value endpoints (returns {"description":"...","value":"..."})
        "/apiv2/hubs/$hub_hash/attributes/fanc",
        "/apiv2/hubs/$hub_hash/attributes/speedc",
        "/apiv2/hubs/$hub_hash/attributes/roomnamec",
        # Sensor list (returns capability flags)
        "/apiv2/hubs/$hub_hash/sensors",
        # Individual sensor value endpoints (expected format: {"description":"...","value":"..."})
        "/apiv2/hubs/$hub_hash/sensors/fillc",
        "/apiv2/hubs/$hub_hash/sensors/rfidc",
        "/apiv2/hubs/$hub_hash/sensors/wific",
        "/apiv2/hubs/$hub_hash/sensors/versionc",
        "/apiv2/hubs/$hub_hash/sensors/battc",

    );

    for my $path (@paths) {
        my $req = HTTP::Request->new( GET => "https://rituals.sense-company.com$path" );
        $req->header( Authorization => $token );
        my $resp = $ua->request($req);
        $out .= "GET $path
";
        $out .= "-> HTTP " . $resp->code . " " . $resp->message . "
";
        if ($resp->code != 404 && $resp->code != 401) {
            $out .= $resp->decoded_content . "
";
        }
        $out .= "
";
    }
    return $out;
}

sub fetch_raw_attributes {
    my ($hub_hash) = @_;
    return '{"error":"No hub hash"}' unless $hub_hash;
    return '{"error":"No token"}' unless -f $token_file;
    my $td    = load_json($token_file);
    my $token = $td->{eva_token} // '';
    return '{"error":"No eva_token"}' unless $token;

    my $ua  = LWP::UserAgent->new( agent => 'Rituals2Lox/0.1', timeout => 15 );
    my $out = "Attribute endpoints for hub: $hub_hash
" . "=" x 60 . "

";

    # List of known attribute names (from hub.attributes capability flags)
    my @attr_names = qw(fanc speedc roomnamec roomc fspacenamec fspacetypec ledc squaremeterc resetc);

    for my $name (@attr_names) {
        my $req = HTTP::Request->new( GET =>
            "https://rituals.sense-company.com/apiv2/hubs/$hub_hash/attributes/$name" );
        $req->header( Authorization => $token );
        my $resp = $ua->request($req);
        $out .= "GET /apiv2/hubs/.../attributes/$name
";
        $out .= "-> HTTP " . $resp->code . " " . $resp->message . "
";
        $out .= $resp->decoded_content . "

" if $resp->is_success;
        $out .= "
" unless $resp->is_success;
    }
    return $out;
}

sub get_token_status {
    unless (-f $token_file) {
        return ( AUTH_NONE => 1, AUTH_VALID => 0, AUTH_EXPIRED => 0 );
    }
    my $d    = load_json($token_file);
    my $exp  = $d->{expires_at} // 0;
    my $fet  = $d->{fetched_at} // 0;
    my $left = $exp - time();
    my $fetched_str = '' . localtime($fet);
    my $expires_str = '' . localtime($exp);
    if ($left > 0) {
        # Warn if token has suspiciously long TTL (> 60 min = old long-TTL token on disk)
        my $ttl_warn = ($left > 3600) ? 1 : 0;
        return (
            AUTH_NONE      => 0, AUTH_VALID => 1, AUTH_EXPIRED => 0,
            TOKEN_MIN_LEFT => int($left / 60),
            TOKEN_FETCHED  => $fetched_str,
            TOKEN_EXPIRES  => $expires_str,
            TOKEN_TTL_WARN => $ttl_warn,
        );
    }
    return ( AUTH_NONE => 0, AUTH_VALID => 0, AUTH_EXPIRED => 1, TOKEN_FETCHED => $fetched_str );
}

sub sanitize {
    my ($s) = @_;
    $s = lc $s; $s =~ s/[^a-z0-9]+/_/g; $s =~ s/^_|_$//g;
    return $s || 'genie';
}

sub load_json {
    my ($f) = @_;
    return {} unless -f $f;
    open(my $fh, '<', $f) or return {};
    local $/; my $raw = <$fh>; close $fh;
    return eval { decode_json($raw) } // {};
}

sub save_json {
    my ($f, $d) = @_;
    open(my $fh, '>', $f) or do { LOGERR("Cannot write $f: $!"); return; };
    print $fh encode_json($d);
    close $fh;
}
