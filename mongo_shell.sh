#!/usr/bin/env bash
sudo docker run --link rhino_mongo_dev:mongo -i -t mongo mongo --host mongo