#!/usr/bin/perl
# Rituals2Lox - State endpoint (PUBLIC, no auth)
# Loxone Virtual HTTP Input polls this for each field value.
#
# Usage:
#   GET /plugins/rituals2lox/state.cgi?hub=HASH&field=on    ? "1"
#   GET /plugins/rituals2lox/state.cgi?hub=HASH&field=fill  ? "75"
#   GET /plugins/rituals2lox/state.cgi?hub=all              ? JSON of all hubs
#
# Loxone Check pattern for each field:  \v
# (the entire response body IS the value)

use strict;
use warnings;
use CGI;
use JSON;

use constant {
    CACHE_FILE => 'REPLACELBPDATADIR/hubs_cache.json',
};

my $cgi   = CGI->new;
my $hub   = $cgi->param('hub')   // '';
my $field = $cgi->param('field') // '';

# Load cache
my $cache = [];
if (-f CACHE_FILE) {
    open(my $fh, '<:encoding(UTF-8)', CACHE_FILE) or do {
        print "Content-Type: text/plain\n\n-1"; exit;
    };
    local $/; my $raw = <$fh>; close $fh;
    my $d = eval { decode_json($raw) };
    $cache = $d if ref $d eq 'ARRAY';
}

# Return all hubs as JSON
if ($hub eq 'all' || !$hub) {
    print "Content-Type: application/json\n";
    print "Cache-Control: no-cache\n\n";
    print encode_json($cache);
    exit;
}

# Find the specific hub
my $hub_data;
for my $h (@$cache) {
    if (($h->{hash} // '') eq $hub) {
        $hub_data = $h;
        last;
    }
}

unless ($hub_data) {
    print "Content-Type: text/plain\n\nERROR: hub not found";
    exit;
}

# Return single field value as plain text
print "Content-Type: text/plain\n";
print "Cache-Control: no-cache\n\n";

if (!$field) {
    print encode_json($hub_data);
    exit;
}

my $val = $hub_data->{$field};
if (!defined $val) {
    print "-1";
} else {
    # Loxone needs numeric values for analog inputs
    print $val;
}
