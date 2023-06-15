#!/bin/bash

sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys D8FF8E1F7DF8B07E
sudo apt-key update

echo "deb https://repos.influxdata.com/ubuntu jammy stable" | sudo tee /etc/apt/sources.list.d/influxdb.list
curl -sL https://repos.influxdata.com/influxdb.key | sudo apt-key add -
