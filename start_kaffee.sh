#!/bin/bash
sleep 5
# 1. Gehe in den Ordner, wo deine Python-Dateien liegen
cd /home/pi/kaffee_projekt
#Bildschirmschoner deaktivereen
xset s noblank
xset s off
xset -dpms
# 3. Starte danach sofort die grafische Oberfläche
python3 kaffee_system_main.py
