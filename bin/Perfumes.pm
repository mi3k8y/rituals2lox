package Perfumes;
# Rituals2Lox - fragrance code table.
#
# The Rituals API returns the cartridge as a name (rfidc.title). Loxone virtual
# inputs cannot show text, so the plugin sends a stable integer code instead and
# the user translates it in Loxone Config.
#
#   0        no cartridge / no reading
#   1..99    built-in codes (never renumbered between releases)
#   100+     cartridges not in the built-in list: assigned automatically the first
#            time they are seen and stored in perfumes.json (codes never change)
#
# Matching ignores case and filler words, so "The Ritual of Jing", "Jing" and
# "Jing Cartridge" are all the same fragrance.

use strict;
use warnings;
use utf8;
use JSON;

# code => display name. NEVER renumber or reuse a code; only append.
my @SEED = (
    [  1, 'The Ritual of Sakura'  ],
    [  2, 'The Ritual of Jing'    ],
    [  3, 'The Ritual of Ayurveda'],
    [  4, 'The Ritual of Karma'   ],
    [  5, 'The Ritual of Hammam'  ],
    [  6, 'The Ritual of Yozakura'],
    [  7, 'Mystic Cedar'          ],
    [  8, 'Royal Tea'             ],
    [  9, 'Sweet Jasmine'         ],
    [ 10, 'Precious Amber'        ],
    [ 11, 'Savage Garden'         ],
    [ 12, 'Suede Vanilla'         ],
    [ 13, 'Cotton Blossom'        ],
);

# Titles that mean "nothing in the diffuser" -> code 0
my %ZERO = map { $_ => 1 } (
    'none', 'no cartridge', 'no perfume', 'no fragrance', 'unknown',
    'n a', 'not available', 'no measurement available',
);

my %SEED;
for my $s (@SEED) { $SEED{ normalize($s->[1]) } = { code => $s->[0], name => $s->[1] }; }

sub normalize {
    my ($t) = @_;
    return '' unless defined $t;
    my $s = lc $t;
    $s =~ s/[^\p{L}\p{N}]+/ /g;
    $s =~ s/\bthe ritual of\b/ /g;
    $s =~ s/\britual of\b/ /g;
    $s =~ s/\b(?:private collection|perfume diffuser|diffuser|refill|cartridge|genie)\b/ /g;
    $s =~ s/\b\d+ ?ml\b/ /g;
    $s =~ s/\s+/ /g;
    $s =~ s/^ | $//g;
    return $s;
}

sub _load {
    my ($file) = @_;
    return {} unless defined $file && -f $file;
    open(my $fh, '<:raw', $file) or return {};
    local $/; my $raw = <$fh>; close $fh;
    my $d = eval { JSON->new->utf8->decode($raw) };
    return (ref $d eq 'HASH') ? $d : {};
}

sub _save {
    my ($file, $data) = @_;
    my $tmp = "$file.tmp$$";
    open(my $fh, '>:raw', $tmp) or return 0;
    print $fh JSON->new->utf8->canonical->pretty->encode($data);
    close $fh or return 0;
    return rename($tmp, $file);
}

# Fragrance title -> integer code. Learns unknown fragrances (persisted in $file).
sub code_for {
    my ($title, $file) = @_;
    my $key = normalize($title);
    return 0 if $key eq '' || $ZERO{$key};
    return $SEED{$key}{code} if $SEED{$key};

    my $learned = _load($file);
    return $learned->{$key}{code} if ref $learned->{$key} eq 'HASH' && defined $learned->{$key}{code};

    my $max = 99;
    for my $v (values %$learned) {
        $max = $v->{code} if ref $v eq 'HASH' && defined $v->{code} && $v->{code} > $max;
    }
    my $code = $max + 1;
    $learned->{$key} = { code => $code, name => $title };
    _save($file, $learned) if defined $file;
    return $code;
}

# List for the web UI / help: [ { code, name, source } ], sorted by code.
sub table {
    my ($file) = @_;
    my @rows = ( { code => 0, name => 'No cartridge / no reading', source => 'built-in' } );
    push @rows, map { { code => $_->[0], name => $_->[1], source => 'built-in' } } @SEED;
    my $learned = _load($file);
    for my $k (sort { $learned->{$a}{code} <=> $learned->{$b}{code} }
               grep { ref $learned->{$_} eq 'HASH' && defined $learned->{$_}{code} } keys %$learned) {
        push @rows, { code => $learned->{$k}{code}, name => $learned->{$k}{name} // $k, source => 'learned' };
    }
    return @rows;
}

1;
