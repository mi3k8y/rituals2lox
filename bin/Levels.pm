package Levels;
# Rituals2Lox - convert the text levels returned by the Rituals API to numbers.
#
# The API reports the cartridge level as text, e.g. "Full", "Empty" or a range
# such as "40-50%". Loxone needs a number, so a range becomes its midpoint
# (40-50% -> 45), a single percentage is used as is, and -1 means "no reading".

use strict;
use warnings;

my %FILL_TEXT = (
    'full'                     => 100,
    'half'                     => 50,
    'low'                      => 25,
    'empty'                    => 0,
    'no measurement available' => -1,
);

sub fill {
    my ($title) = @_;
    return -1 unless defined $title;
    (my $t = $title) =~ s/^\s+|\s+$//g;
    return -1 if $t eq '';

    # "40-50%", "40 - 50 %", "0-10" (hyphen, en dash or "to")
    if ($t =~ /^(\d{1,3})\s*(?:-|to|\x{2013}|\x{2014})\s*(\d{1,3})\s*%?$/i) {
        my ($lo, $hi) = ($1 <= $2) ? ($1, $2) : ($2, $1);
        return -1 if $hi > 100;
        return int(($lo + $hi) / 2);
    }
    # "45%" or "45"
    if ($t =~ /^(\d{1,3})\s*%?$/) {
        return $1 <= 100 ? int($1) : -1;
    }
    my $k = lc $t;
    return exists $FILL_TEXT{$k} ? $FILL_TEXT{$k} : -1;
}

1;
