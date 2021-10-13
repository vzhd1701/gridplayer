#!/bin/bash

CHANGELOG=$1

sed "1,/### \[/d;/### \[/Q" "$CHANGELOG"
