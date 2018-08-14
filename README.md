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
    strip2:
      name: "LED Stripe 2"     # optional
      host: "192.168.2.151"
      max_brightness: 125      # optional
      calibration_factor:      # optional
        red: 0.39              # optional
        green: 0.157           # optional
        blue: 0.196            # optional
        warmwhite: 1           # optional
        coldwhite: 1           # optional
```
