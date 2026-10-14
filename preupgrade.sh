#!/bin/bash
COMMAND=$0
PTEMPDIR=$1
PSHNAME=$2
PDIR=$3
PVERSION=$4
PTEMPPATH=$6

PDATA=$LBPDATA/$PDIR

echo "<INFO> Backing up plugin data before upgrade"
mkdir -p $PTEMPPATH/upgrade/data

for f in credentials.json token.json config.json; do
    if [ -f "$PDATA/$f" ]; then
        cp -p $PDATA/$f $PTEMPPATH/upgrade/data/
        echo "<INFO> Backed up $f"
    fi
done

echo "<OK> Pre-upgrade backup complete."
exit 0
