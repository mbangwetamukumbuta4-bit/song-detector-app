[app]
title = Wenzosong Detector
package.name = songdetector
package.domain = org.songdetector
source.dir = .
source.include_exts = py,png,jpg,kv,json
version = 0.1
requirements = python3,kivy==2.3.0,pyjnius,android,certifi
orientation = portrait
fullscreen = 0
android.permissions = RECORD_AUDIO,INTERNET,READ_EXTERNAL_STORAGE,READ_MEDIA_AUDIO
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.ndk = 25b
p4a.branch = v2024.01.21
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/icon.png
android.presplash_color = #1A2E6C

[buildozer]
log_level = 2
warn_on_root = 1
