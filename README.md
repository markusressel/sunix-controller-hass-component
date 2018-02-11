# ha-sunix-controller
Home Assistant custom component for the Sunix WiFi RGBW controller

# Configuration (yaml)

```
light:
- platform: sunix_rgbw_led
  devices:
    strip1:
      name: "LED Stripe 1"     # optional
      host: "192.168.2.150"
      max_brightness: 125      # optional
      calibration_offset:      # optional
        red: 0                 # optional
        green: -50             # optional
        blue: 20               # optional
    strip2:
      name: "LED Stripe 2"     # optional
      host: "192.168.2.151"
      max_brightness: 125      # optional
      calibration_offset:      # optional
        red: 0                 # optional
        green: -50             # optional
        blue: 20               # optional
      
  - platform: sunix_rgbw_led
    name: "LED Stripe"        # optional
    host: 192.168.2.150
    port: 32891               # optional
    calibration_offset:       # optional
      red: 0                  # optional
      green: -50              # optional
      blue: 20                # optional
```
