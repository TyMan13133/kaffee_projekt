#!/bin/bash

# 1. Gehe in den Ordner, wo deine Python-Dateien liegen
cd /home/pi/kaffee_projekt

# 2. Starte die app.py im Hintergrund (das & am Ende ist extrem wichtig!)
python3 app.py &

# 3. Starte danach sofort die grafische Oberfläche
python3 kaffee_system_main.py
