#!/usr/bin/perl
# Rituals2Lox  -  Token Manager
#
# Rituals EVA tokens expire after exactly 60 minutes.
# Rate limit: max 5 authentication requests per hour.
#
# Strategy:
#   - TOKEN_TTL = 3600s (60 min) - matches actual API token lifetime
#   - REFRESH_MARGIN = 300s (5 min) - refresh when < 5 min remain
#   - cron.30min runs "check" every 30 min
#   - "check" calls the API only when token has < 5 min left
#   - This means 1 API call per 60 min = 24 calls/day = well under 5/hour limit
#
# Usage:
#   token-manager.pl refresh   -  fetch new token unconditionally (use sparingly!)
#   token-manager.pl check     -  fetch only if token expires within REFRESH_MARGIN
#   token-manager.pl status    -  print token status to log and stdout

use strict;
use warnings;
use LWP::UserAgent;
use HTTP::Request;
use JSON;
use LoxBerry::Log;

use constant {
    TOKEN_ENDPOINT => 'https://rituals.apiv2.sense-company.com/apiv2/account/token',
    TOKEN_TTL      => 2700,  # 45 min - conservative TTL (API token lasts 60 min)
    REFRESH_MARGIN => 300,   # refresh when < 5 min remain (safe buffer)
    CREDS_FILE     => 'REPLACELBPDATADIR/credentials.json',
    TOKEN_FILE     => 'REPLACELBPDATADIR/token.json',
    TOKEN_TMP      => 'REPLACELBPDATADIR/token.json.tmp',
};

my $log = LoxBerry::Log->new( name => 'token-manager', addtime => 1, loglevel => 6 );

my $command = $ARGV[0] || 'check';
LOGSTART("Rituals2Lox Token Manager  -  $command");

if    ($command eq 'refresh') { exit do_refresh(); }
elsif ($command eq 'check')   { exit do_check();   }
elsif ($command eq 'status')  { exit do_status();  }
else {
    LOGERR("Unknown command '$command'. Use: refresh | check | status");
    LOGEND; exit 1;
}

# -- Commands ------------------------------------------------------------------

sub do_refresh {
    LOGINF("Forcing token refresh (manual request).");
    my $ok = fetch_and_store();
    LOGEND; return $ok ? 0 : 1;
}

sub do_check {
    LOGINF("Running at " . localtime(time()) . "  (cron.30min)");
    if (-f TOKEN_FILE) {
        my $d    = load_json(TOKEN_FILE);
        unless ($d && $d->{eva_token}) {
            LOGWARN("token.json exists but is empty or unreadable  -  forcing refresh.");
            $d = {};
        }
        my $left = ($d->{expires_at} // 0) - time();
        if ($left > REFRESH_MARGIN) {
            my $exp_str = localtime($d->{expires_at});
            LOGINF("Token valid for " . int($left/60) . " min  -  no refresh needed.");
            LOGINF("Expires at: $exp_str  (expires_at=" . ($d->{expires_at}//0) . " now=" . time() . ")");
            LOGEND; return 0;
        }
        if ($left > 0) {
            LOGINF("Token expires in " . int($left/60) . " min  -  refreshing now.");
        } else {
            LOGINF("Token expired " . int(-$left/60) . " min ago  -  refreshing now.");
        }
    } else {
        LOGINF("No token file  -  fetching initial token.");
    }
    my $ok = fetch_and_store();
    LOGEND; return $ok ? 0 : 1;
}

sub do_status {
    unless (-f TOKEN_FILE) {
        LOGWARN("No token file found.");
        print "NONE\n";
        LOGEND; return 1;
    }
    my $d    = load_json(TOKEN_FILE);
    my $left = ($d->{expires_at} // 0) - time();
    my $min  = int($left / 60);
    if ($left > 0) {
        LOGINF("VALID  -  expires in ${min} min");
        print "VALID\nexpires_in_min=$min\nfetched_at=" . ($d->{fetched_at}//0) . "\n";
    } else {
        LOGWARN("EXPIRED  -  " . int(-$left/60) . " min ago");
        print "EXPIRED\n";
    }
    LOGEND; return 0;
}

# -- Core: fetch token and write atomically ------------------------------------

sub fetch_and_store {
    unless (-f CREDS_FILE) {
        LOGERR("credentials.json not found. Configure email/password in the plugin UI.");
        return 0;
    }
    my $creds = load_json(CREDS_FILE);
    unless ($creds->{email} && $creds->{password}) {
        LOGERR("credentials.json is missing email or password.");
        return 0;
    }

    LOGINF("Calling Rituals API for new token.");
    my $ua = LWP::UserAgent->new( agent => 'Rituals2Lox/0.1', timeout => 15 );
    push @{ $ua->requests_redirectable }, 'POST';   # follow 307/308 redirects on POST

    my $json_body = encode_json({ email => $creds->{email}, password => $creds->{password} });
    my $req = HTTP::Request->new( POST => TOKEN_ENDPOINT );
    $req->header( 'Content-Type' => 'application/json' );
    $req->content( $json_body );

    my $resp = $ua->request($req);

    unless ($resp->is_success) {
        LOGERR("Rituals API HTTP " . $resp->code . ": " . $resp->status_line);
        LOGERR("Response body: " . substr($resp->decoded_content // '', 0, 200));
        return 0;
    }

    my $body = eval { decode_json($resp->decoded_content) };
    if ($@) { LOGERR("JSON parse error: $@"); return 0; }

    my $token = $body->{success};
    unless ($token) {
        LOGERR("API response missing 'success' key. Got: " . $resp->decoded_content);
        return 0;
    }

    my $now = time();
    my $payload = encode_json({
        eva_token  => $token,
        fetched_at => $now,
        expires_at => $now + TOKEN_TTL,
    });

    open(my $fh, '>', TOKEN_TMP) or do { LOGERR("Cannot write tmp: $!"); return 0; };
    print $fh $payload;
    close $fh;

    rename(TOKEN_TMP, TOKEN_FILE) or do {
        LOGERR("Atomic rename failed: $!"); unlink TOKEN_TMP; return 0;
    };
    chmod 0600, TOKEN_FILE;

    LOGINF("Token stored. Valid for 45 min until " . localtime($now + TOKEN_TTL) . ".");
    return 1;
}

# -- Helpers -------------------------------------------------------------------

sub load_json {
    my ($f) = @_;
    return {} unless -f $f;
    open(my $fh, '<', $f) or return {};
    local $/; my $raw = <$fh>; close $fh;
    return eval { decode_json($raw) } // {};
}
