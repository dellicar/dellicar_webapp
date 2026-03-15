#!/bin/bash
cd ~/Desktop/dellicar_webapp
mkdir -p backup
cp dellicar.db backup/dellicar_$(date +%Y-%m-%d_%H-%M-%S).db
