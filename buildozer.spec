[app]
title = Song Detector
package.name = songdetector
package.domain = org.songdetector
source.dir = .
source.include_exts = py,png,jpg,kv,json
version = 0.1
requirements = python3,kivy==2.3.0,pyjnius,android,certifi
orientation = portrait
fullscreen = 0
android.permissions = RECORD_AUDIO,INTERNET
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.ndk = 25b
p4a.branch = v2024.01.21
[buildozer]
log_level = 2
warn_on_root = 1
