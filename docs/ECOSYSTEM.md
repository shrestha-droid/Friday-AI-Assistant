# The ecosystem: J.A.R.V.I.S., FRIDAY, E.D.I.T.H. and the hardware

Nothing in this file is built yet except the software brain. The hardware parts lists are starting points:
check current prices and specs before you buy anything.

## Who is who

| Name | Where it lives | Personality | Built? |
|---|---|---|---|
| **J.A.R.V.I.S.** | the hub (this server) | dry British butler, the orchestrator | persona yes, orchestration no |
| **FRIDAY** | your Mac, desk, daily tasks | sharp, warm, cheeky | yes |
| **E.D.I.T.H.** | the smart glasses | tactical, brisk callouts, sees what you see | persona yes, glasses no |
| **Ultron** | under all of them | silk-voiced raconteur, only when there is one option left | yes, as an undertone |

The rule that keeps the story honest: **one brain, many bodies**. Devices are thin. They capture audio, images and sensor
readings, send them to the hub, and play back what the hub says. All memory, safety rules and personality stay in `friday/`.

## The device protocol (to build next)

One WebSocket per device, `wss://<hub>/ws/device`, JSON text frames plus binary frames for audio and images.
It reuses the existing agent, so a glasses question goes through the same permission and audit path as the browser.

```
device -> hub   {"t":"hello","device":"edith-glasses-1","persona":"edith","caps":["mic","cam","speaker","button"]}
device -> hub   {"t":"say","text":"what is this?","image":"<jpeg base64, optional>"}      # after on-device wake or button
device -> hub   {"t":"event","name":"mat.pressure","value":0.8}                           # sensors
hub -> device   {"t":"speak","text":"A resistor, 4.7k ohm.","mood":"normal"}               # device does TTS or plays audio
hub -> device   {"t":"cmd","name":"led","value":"#ff3b57"}                                 # the Ultron colour shift, on hardware
hub -> device   {"t":"confirm","summary":"...","action_id":"..."}                          # approval on a button or the phone
```

Auth is a per-device token issued by the hub (never the browser cookie). A device never gets tools of its own;
it can only talk to the agent. `mood:"ultron"` is how every body knows to change voice and colour.

## E.D.I.T.H. glasses: build in two stages

**v1: camera, mic, speaker, no display** (achievable, and it works from day one)

| Part | Why |
|---|---|
| Seeed XIAO ESP32-S3 Sense | ESP32-S3 with camera and PDM microphone on one tiny board, Wi-Fi + BLE |
| MAX98357A I2S amplifier + small speaker or bone-conduction transducer | audio out |
| 1 x 300 to 500 mAh LiPo + charger board | power, expect an hour or two of continuous use |
| 1 touch pad or tact button | push to talk, since an always-on wake word drains the battery |
| 3D-printed frame, parametric in OpenSCAD | board and battery in the temple arms, camera at the bridge |

Firmware loop: button press, record a few seconds, grab a JPEG, send to the hub, play back the reply.
The community "OpenGlass" project (ESP32-S3 camera + mic in a glasses frame) is a good reference to study first.

**v2: add a display.** The honest options, easiest first: (1) buy open developer glasses with a real display and an SDK
(Brilliant Labs Frame is the one to look at) and write only software; (2) a tiny OLED with a prism or combiner in the frame
(hobby-grade, expect several failed optics attempts). A see-through full-colour display is the hardest part of the whole ecosystem.

## Smart table mat

Capacitive or FSR sensor grid (a 4 x 4 or 6 x 6 matrix is plenty) read by an ESP32, WS2812 LEDs under a thin diffuser sheet,
all hidden under a felt or leather top. It sends `event` frames: which zone is pressed, what is placed on it (weight),
and receives `cmd` frames to light zones. Ideas that fit the personas: a coaster zone that reminds you to drink water,
a phone-charging zone that mutes alerts (focus mode already exists), and the whole mat glowing red for a moment when Ultron speaks.

## Desk robot

ESP32-S3 + two or three SG90/MG90S servos (head turn and tilt, optional arm), a round GC9A01 display for eyes, a speaker,
and a touch sensor on top. The face is a small animation set keyed to the same four states as the orb
(idle, listening, thinking, speaking), plus the crimson one. It is the easiest body after the mat, because it needs no battery and no optics.

## Order of work

1. Finish Friday's remaining items (calendar, streaming speech, wake word).
2. Add `/ws/device` and a fake device script that proves the protocol end to end.
3. Mat (cheapest, quickest win), then desk robot, then glasses v1, then glasses v2.
4. J.A.R.V.I.S. orchestration: one request that fans out to several bodies ("EDITH, scan this; FRIDAY, log it").
