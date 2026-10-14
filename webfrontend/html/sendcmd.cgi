#!/usr/bin/perl
# Rituals2Lox - Command Bridge (PUBLIC, no auth required)
#
# Confirmed API format from Postman docs:
#   POST /apiv2/hubs/{hash}/attributes/{attr_name}
#   Content-Type: application/x-www-form-urlencoded
#   Body: {attr_name}={value}    ? key is the attribute name, NOT "value"
#
# Example: turn on at speed 3:
#   POST /apiv2/hubs/{hash}/attributes/fanc    body: fanc=1
#   POST /apiv2/hubs/{hash}/attributes/speedc  body: speedc=3

use strict;
use warnings;
use CGI;
use LWP::UserAgent;
use HTTP::Request;
use JSON;
use URI::Escape qw(uri_escape);
use LoxBerry::Log;

use constant {
    API_BASE   => 'https://rituals.sense-company.com/apiv2',
    TOKEN_FILE => 'REPLACELBPDATADIR/token.json',
};

my $log = LoxBerry::Log->new( name => 'sendcmd', addtime => 1 );

my $cgi       = CGI->new;
my $command   = lc($cgi->param('command')   // '');
my $hub       = $cgi->param('hub')          // '';
my $intensity = int($cgi->param('intensity') // $cgi->param('value') // 2);
my $debug     = $cgi->param('debug') ? 1 : 0;

# Debug mode - show curl equivalents
if ($debug) {
    print "Content-Type: text/plain\n\n";
    my $token  = read_token() // 'NO_TOKEN';
    my $tshort = substr($token, 0, 8) . '...';
    my $speed  = clamp($intensity);
    print "=== Rituals2Lox sendcmd - confirmed API format ===\n\n";
    print "# Turn ON at intensity $speed:\n";
    print "curl -X POST 'https://rituals.sense-company.com/apiv2/hubs/$hub/attributes/fanc' \\\n";
    print "  -H 'Authorization: $tshort' \\\n";
    print "  --data-urlencode 'fanc=1'\n\n";
    print "curl -X POST 'https://rituals.sense-company.com/apiv2/hubs/$hub/attributes/speedc' \\\n";
    print "  -H 'Authorization: $tshort' \\\n";
    print "  --data-urlencode 'speedc=$speed'\n\n";
    print "# Turn OFF:\n";
    print "curl -X POST 'https://rituals.sense-company.com/apiv2/hubs/$hub/attributes/fanc' \\\n";
    print "  -H 'Authorization: $tshort' \\\n";
    print "  --data-urlencode 'fanc=0'\n";
    exit;
}

print "Content-Type: application/json\n";
print "Access-Control-Allow-Origin: *\n\n";

unless ($command && $hub) {
    print encode_json({ ok => 0, error => 'Missing command or hub' }); exit;
}

my $token = read_token();
unless ($token) {
    print encode_json({ ok => 0, error => 'No valid EVA token - refresh token first' }); exit;
}

my $ua = LWP::UserAgent->new( agent => 'Rituals2Lox/0.1', timeout => 10 );
my ($ok, $msg) = dispatch($command, $hub, $intensity, $token, $ua);

if ($ok) {
    LOGINF("OK: $command hub=...${\substr($hub,-8)}");
    print encode_json({ ok => 1, message => $msg });
} else {
    LOGWARN("FAIL: $command - $msg");
    print encode_json({ ok => 0, error => $msg });
}

# -- Dispatch --------------------------------------------------------------------

sub dispatch {
    my ($cmd, $hub_hash, $int, $token, $ua) = @_;
    my $speed = clamp($int);

    if ($cmd eq 'on') {
        my ($ok1, $m1) = post_attribute($hub_hash, 'fanc',   '1',      $token, $ua);
        my ($ok2, $m2) = post_attribute($hub_hash, 'speedc', "$speed", $token, $ua);
        return (1, "ON speed=$speed") if $ok1 && $ok2;
        return (0, "fanc: $m1 / speedc: $m2");

    } elsif ($cmd eq 'off') {
        return post_attribute($hub_hash, 'fanc', '0', $token, $ua);

    } elsif ($cmd eq 'intensity') {
        return post_attribute($hub_hash, 'speedc', "$speed", $token, $ua);

    } else {
        return (0, "Unknown command: $cmd");
    }
}

# POST /apiv2/hubs/{hash}/attributes/{attr}
# Body (form-encoded): {attr}={value}   ? key IS the attribute name
sub post_attribute {
    my ($hub_hash, $attr, $value, $token, $ua) = @_;

    my $url  = API_BASE . "/hubs/$hub_hash/attributes/$attr";
    my $body = uri_escape($attr) . '=' . uri_escape($value);

    my $req = HTTP::Request->new( POST => $url );
    $req->header( 'Authorization' => $token );
    $req->header( 'Content-Type'  => 'application/x-www-form-urlencoded' );
    $req->content( $body );

    my $resp = $ua->request($req);
    my $rbody = substr($resp->decoded_content // '', 0, 300);

    LOGINF("POST /attributes/$attr body=$body ? HTTP " . $resp->code . " $rbody");

    return (1, 'OK')                              if $resp->is_success;
    return (0, 'Unauthorized')                    if $resp->code == 401;
    return (0, 'HTTP ' . $resp->code . ": $rbody");
}

# -- Helpers ---------------------------------------------------------------------

sub read_token {
    return undef unless -f TOKEN_FILE;
    open(my $fh, '<', TOKEN_FILE) or return undef;
    local $/; my $raw = <$fh>; close $fh;
    my $d = eval { decode_json($raw) } // {};
    return $d->{eva_token} || undef;
}

sub clamp { my $v = int($_[0] // 2); $v < 1 ? 1 : $v > 3 ? 3 : $v }
