#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
apt-get install --fix-broken -y -o Dpkg::Options::="--force-overwrite"
apt-get install -y python3-opencv
