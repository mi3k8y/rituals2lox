#!/bin/bash
COMMAND=$0
PTEMPDIR=$1
PSHNAME=$2
PDIR=$3
PVERSION=$4
PTEMPPATH=$6

PDATA=$LBPDATA/$PDIR
PBIN=$LBPBIN/$PDIR
PHTMLAUTH=$LBHOMEDIR/webfrontend/htmlauth/plugins/$PDIR

echo "<INFO> Restoring persisted data"
if [ -d "$PTEMPPATH/upgrade/data" ]; then
    cp -p -v -r $PTEMPPATH/upgrade/data/* $PDATA/ 2>/dev/null || true
fi

echo "<INFO> Re-securing sensitive files"
if [ -f "$PDATA/credentials.json" ]; then chmod 600 $PDATA/credentials.json; fi
if [ -f "$PDATA/token.json" ]; then chmod 600 $PDATA/token.json; fi

echo "<INFO> Restoring script permissions"
chmod 755 $PBIN/token-manager.pl
chmod 755 $PBIN/grabber.pl
chmod 755 $PHTMLAUTH/index.cgi
chmod 755 $PHTMLAUTH/sendcmd.cgi

rm -rf $PTEMPPATH/upgrade

echo "<OK> Rituals2Lox upgrade complete."
exit 0
