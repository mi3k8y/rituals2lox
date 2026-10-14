#!/bin/bash
COMMAND=$0
PTEMPDIR=$1
PSHNAME=$2
PDIR=$3
PVERSION=$4
PTEMPPATH=$6

PHTMLAUTH=$LBHOMEDIR/webfrontend/htmlauth/plugins/$PDIR
PHTML=$LBHOMEDIR/webfrontend/html/plugins/$PDIR
PBIN=$LBPBIN/$PDIR
PDATA=$LBPDATA/$PDIR
PCONFIG=$LBPCONFIG/$PDIR

echo "<INFO> Setting permissions for bin scripts"
chmod 755 $PBIN/token-manager.pl
chmod 755 $PBIN/grabber.pl

echo "<INFO> Setting permissions for cron scripts"
PCRON=$LBHOMEDIR/system/cron
chmod 755 $PCRON/cron.01min/rituals2lox 2>/dev/null || true
chmod 755 $PCRON/cron.30min/rituals2lox 2>/dev/null || true

echo "<INFO> Setting permissions for CGI scripts (authenticated)"
chmod 755 $PHTMLAUTH/index.cgi
chmod 755 $PHTMLAUTH/sendcmd.cgi

echo "<INFO> Setting permissions for public CGI scripts"
chmod 755 $PHTML/sendcmd.cgi
chmod 755 $PHTML/state.cgi

echo "<INFO> Securing data directory"
chmod 700 $PDATA

if [ -f "$PDATA/credentials.json" ]; then
    chmod 600 $PDATA/credentials.json
fi
if [ -f "$PDATA/token.json" ]; then
    chmod 600 $PDATA/token.json
fi

echo "<INFO> Creating empty config if not exists"
if [ ! -f "$PDATA/config.json" ]; then
    echo '{}' > $PDATA/config.json
    chmod 644 $PDATA/config.json
fi

if [ ! -f "$PDATA/hubs_cache.json" ]; then
    echo '[]' > $PDATA/hubs_cache.json
    chmod 644 $PDATA/hubs_cache.json
fi

# Remove stale token.json and immediately fetch fresh token with correct 60min TTL
if [ -f "$PDATA/token.json" ]; then
    echo "<INFO> Removing old token.json to force fresh 60-min TTL token"
    rm -f "$PDATA/token.json"
fi

# Fetch fresh token immediately if credentials exist
if [ -f "$PDATA/credentials.json" ]; then
    echo "<INFO> Fetching fresh authentication token..."
    export PERL5LIB=$LBHOMEDIR/libs/perllib
    perl $PBIN/token-manager.pl refresh >> $LBPLOG/$PDIR/token-manager.log 2>&1 &&         echo "<OK> Token fetched successfully." ||         echo "<WARN> Token fetch failed. Use Refresh Token Now in plugin UI."
fi

echo "<OK> Rituals2Lox installed successfully. Version $PVERSION"
exit 0
