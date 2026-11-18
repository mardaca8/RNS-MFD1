#!/bin/bash
# RNS-MFD1 wireless Android Auto installer for Raspberry Pi 3B+ (Raspberry Pi OS Lite trixie)
#
#   git clone https://github.com/maltsevvv/repository.git
#   sudo bash repository/androidauto/install.sh
#
# Builds opencardev/aasdk + opencardev/openauto on the Pi (takes 1-3 hours on a 3B+).

user="$SUDO_USER"
SRC="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$SRC")"
BUILD=/opt/openauto-build

# Versions this setup was written against
AASDK_REF=9bf6adf933665dee26532201719fac14a047ccf1
OPENAUTO_REF=4cc739b813622739b09352655581072fc4d39280

# Function for green text output
green() {
    printf "\033[32m%s\033[0m\n" "$1"
}
# Function for red text output
red() {
    printf "\033[31m%s\033[0m\n" "$1"
}

if [ -z "$SUDO_USER" ]; then
    red "Error: The script must be run with sudo. Example: sudo bash androidauto/install.sh"
    exit 1
fi

if [ -e /boot/firmware/config.txt ]; then
    CONFIG=/boot/firmware/config.txt
    CMDLINE=/boot/firmware/cmdline.txt
else
    CONFIG=/boot/config.txt
    CMDLINE=/boot/cmdline.txt
fi

check_system() {
    . /etc/os-release
    green "OS: $PRETTY_NAME"
    if [ "$VERSION_CODENAME" != "trixie" ]; then
        red "     Raspberry Pi OS Lite trixie is required (aasdk only supports trixie). ❌"
        exit 1
    fi
    MODEL=$(tr -d '\0' < /proc/device-tree/model)
    green "$MODEL"
    echo "$MODEL" | grep -q "Raspberry Pi 3 Model B Plus" || red "     Made for Raspberry Pi 3B+ (needs its 5 GHz Wi-Fi). Continuing anyway. ⚠️"
}

rpi_backup() {
    echo "Create backup config.txt / cmdline.txt"
    [ -e $CONFIG.backup ] || cp $CONFIG $CONFIG.backup
    [ -e $CMDLINE.backup ] || cp $CMDLINE $CMDLINE.backup
    green "     Backups: $CONFIG.backup $CMDLINE.backup ✅"
}

install_packages() {
    echo "Installing packages..."
    apt-get update
    apt-get install -y \
        python3-can python3-evdev can-utils alsa-utils pulseaudio pulseaudio-utils bluez bluez-firmware bluez-tools bluez-alsa-utils pi-bluetooth hostapd rfkill \
        gstreamer1.0-plugins-base gstreamer1.0-alsa gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav \
        build-essential cmake ninja-build pkg-config git file dpkg-dev fakeroot \
        libboost-all-dev libprotobuf-dev protobuf-compiler libusb-1.0-0-dev libssl-dev libabsl-dev \
        libblkid-dev libgps-dev libtag1-dev librtaudio-dev \
        qtbase5-dev qtmultimedia5-dev qttools5-dev qttools5-dev-tools qtconnectivity5-dev \
        libqt5multimedia5-plugins libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
        || { red "     Package installation failed. ❌"; exit 1; }
    green "     Packages installed. ✅"
}

# 1 GB RAM is not enough to compile openauto
swap_on() {
    if [ ! -f /var/openauto-build.swap ]; then
        fallocate -l 2G /var/openauto-build.swap
        chmod 600 /var/openauto-build.swap
        mkswap /var/openauto-build.swap > /dev/null
    fi
    swapon /var/openauto-build.swap 2> /dev/null
}

swap_off() {
    swapoff /var/openauto-build.swap 2> /dev/null
    rm -f /var/openauto-build.swap
}

checkout() {
    # $1 = repo, $2 = dir, $3 = commit
    if [ ! -d "$2/.git" ]; then
        git clone "https://github.com/$1.git" "$2" || { red "     Clone of $1 failed. ❌"; exit 1; }
    fi
    git -C "$2" reset -q --hard  # drop a previously applied patch
    git -C "$2" fetch -q origin
    git -C "$2" checkout -q "$3" || { red "     Checkout $3 failed. ❌"; exit 1; }
}

# Low-latency video: openauto's QMediaPlayer output lagged ~30 s and used ~175 % CPU on a 3B+
apply_openauto_patch() {
    cp -r "$SRC/openauto-patch/include" "$SRC/openauto-patch/src" $BUILD/openauto/
    cat "$SRC/openauto-patch/CMakeLists.rns.txt" >> $BUILD/openauto/CMakeLists.txt
    green "     openauto low-latency video patch applied. ✅"
}

build_openauto() {
    if command -v autoapp > /dev/null && command -v btservice > /dev/null; then
        if ! whiptail --title "openauto" --yesno "openauto is already installed. Rebuild it?" 8 50; then
            return
        fi
    fi
    green "Building aasdk + openauto. This takes 1-3 hours on a Pi 3B+. ☕"
    mkdir -p $BUILD
    swap_on
    # nproc (used by the build scripts) honours OMP_NUM_THREADS; 2 jobs fit in RAM+swap
    export OMP_NUM_THREADS=2 JOBS=2

    if ! ldconfig -p | grep -q libaasdk; then
        checkout opencardev/aasdk $BUILD/aasdk $AASDK_REF
        (cd $BUILD/aasdk && bash build.sh release package install) || { red "     aasdk build failed. ❌"; swap_off; exit 1; }
        find $BUILD/aasdk -maxdepth 3 -name "*.deb" -newer $BUILD/aasdk/CMakeLists.txt -exec apt-get install -y --allow-downgrades {} +
        ldconfig
    fi

    checkout opencardev/openauto $BUILD/openauto $OPENAUTO_REF
    apply_openauto_patch
    rm -rf $BUILD/debs
    (cd $BUILD/openauto && bash build.sh release --package --output-dir $BUILD/debs) || { red "     openauto build failed. ❌"; swap_off; exit 1; }
    apt-get install -y --allow-downgrades $BUILD/debs/*.deb || { red "     openauto package install failed. ❌"; swap_off; exit 1; }
    swap_off

    # Fall back to the source tree's units if the package did not ship them
    for unit in openauto.service openauto-btservice.service; do
        if [ ! -e /lib/systemd/system/$unit ] && [ ! -e /etc/systemd/system/$unit ]; then
            cp $BUILD/openauto/packaging/systemd/$unit /etc/systemd/system/
        fi
    done
    green "     openauto installed. ✅"
}

rpi_add_can0() {
    echo "Adding MCP2515 can0 ($1 Hz crystal)"
    sed -i '/dtoverlay=mcp2515-can0/d' "$CONFIG"
    sed -i '/dtoverlay=spi-bcm2835/d' "$CONFIG"
    sed -i 's/^#\?dtparam=spi=on/dtparam=spi=on/' "$CONFIG"
    grep -q '^dtparam=spi=on' "$CONFIG" || echo "dtparam=spi=on" >> "$CONFIG"
    echo "dtoverlay=mcp2515-can0,oscillator=$1,interrupt=25" >> "$CONFIG"
    echo "dtoverlay=spi-bcm2835" >> "$CONFIG"

    # VAG infotainment CAN = 100 kbit
    cat > /etc/systemd/network/80-can.network << EOF
[Match]
Name=can0

[CAN]
BitRate=100000
EOF
    systemctl enable systemd-networkd
    green "     can0 @ 100 kbit configured. ✅"
}

rpi_vga() {
    cp "$REPO/driver/rpi480i.bin" "$REPO/driver/rpi240p.bin" /usr/lib/firmware/
    if ! grep -q "hdmi_vga_for_rns" "$CONFIG"; then
        echo " " >> "$CONFIG"
        echo "# hdmi_vga_for_rns" >> "$CONFIG"
        echo "hdmi_ignore_edid=0xa5000080" >> "$CONFIG"
        echo "hdmi_force_hotplug=1" >> "$CONFIG"
        echo "hdmi_group=2" >> "$CONFIG"
        echo "hdmi_mode=87" >> "$CONFIG"
        echo "hdmi_timings=640 0 16 88 64 480 0 6 5 13 0 0 0 60 1 12700000 1" >> "$CONFIG"
        sed -i '/enable_tvout/d' $CONFIG
        sed -i -r 's/(.+),composite/\1/' $CONFIG
    fi
    if ! grep -q 'video=HDMI-A-1:NTSC' "$CMDLINE"; then
        sed -i 's/^/video=HDMI-A-1:NTSC,margin_left=39,margin_right=21,margin_top=17,margin_bottom=27 /' "$CMDLINE"
        sed -i 's/$/ drm.edid_firmware=HDMI-A-1:rpi480i.bin/' "$CMDLINE"
    fi
    # No HDMI audio card, so the 3.5 mm jack is the only sound card
    sed -i 's/^dtoverlay=vc4-kms-v3d.*/dtoverlay=vc4-kms-v3d,noaudio/' $CONFIG
    green "     HDMI-VGA (RGB) video output configured. ✅"
}

rpi_composite() {
    # Pi 3B+ 3.5 mm jack is TRRS: audio L/R + composite video on one plug
    grep -q 'Composite-1' $CMDLINE || sed -i "s/^/video=Composite-1:720x480@60ie /" $CMDLINE
    grep -q 'vc4.tv_norm=' $CMDLINE || sed -i "s/$/ vc4.tv_norm=NTSC/" $CMDLINE
    sed -i 's/^#\?dtoverlay=vc4-kms-v3d.*/dtoverlay=vc4-kms-v3d,composite/' $CONFIG
    grep -q 'enable_tvout' $CONFIG || sed -i '/dtoverlay=vc4-kms-v3d/a\enable_tvout=1' $CONFIG
    sed -i '/hdmi_/d' $CONFIG
    green "     Composite video output (3.5 mm jack) configured. ✅"
}

rpi_audio_jack() {
    sed -i 's/^#\?dtparam=audio=on/dtparam=audio=on/' $CONFIG
    grep -q '^dtparam=audio=on' $CONFIG || echo "dtparam=audio=on" >> $CONFIG
    sed -i "/.*hifiberry-dac.*/d" $CONFIG
    # Straight to the jack: bcm2835 has 8 hardware subdevices, so media + navigation + calls
    # can play together without dmix (dmix stalls on bcm2835)
    cat > /etc/asound.conf << 'EOF'
pcm.!default {
    type plug
    slave.pcm "hw:Headphones"
    # listed by name hints, so Qt picks it instead of the first card (e.g. HDMI)
    hint {
        show on
        description "3.5 mm jack"
    }
}
ctl.!default {
    type hw
    card Headphones
}
EOF
    # openauto's RtAudio output uses PulseAudio. Run one system-wide server that only
    # knows the jack (Qt's own audio output never opened the card here).
    systemctl --global disable pulseaudio.service pulseaudio.socket 2> /dev/null
    cat > /etc/pulse/system.pa << 'EOF'
load-module module-alsa-sink device=hw:Headphones sink_name=jack tsched=0 rate=48000
load-module module-native-protocol-unix auth-anonymous=1
set-default-sink jack
EOF
    cat > /etc/systemd/system/pulseaudio-system.service << 'EOF'
[Unit]
Description=PulseAudio system server (3.5 mm jack)
After=sound.target

[Service]
ExecStart=/usr/bin/pulseaudio --system --disallow-exit --log-target=journal
Restart=always

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable pulseaudio-system.service
    green "     Analog 3.5 mm audio output configured. ✅"
}

# The phone joins this hotspot for wireless Android Auto.
# openauto's btservice reads ssid / wpa_passphrase from /etc/hostapd/hostapd.conf
wifi_hotspot() {
    COUNTRY=$(whiptail --title "Wi-Fi country" --inputbox "Two-letter Wi-Fi country code (e.g. LT, DE, GB):" 8 50 "LT" 3>&1 1>&2 2>&3)
    COUNTRY=${COUNTRY:-LT}
    # Pi 3B+ is dual band. 5 GHz channel 36 (no radar/DFS wait) is what wireless Android Auto prefers.
    if whiptail --title "Hotspot band" --yes-button " 5 GHz " --no-button " 2.4 GHz " --yesno "Wi-Fi band for the phone. 5 GHz is recommended; some phones refuse wireless Android Auto on 2.4 GHz." 10 60; then
        BAND="hw_mode=a\nchannel=36\nieee80211n=1\nieee80211ac=1"
    else
        BAND="hw_mode=g\nchannel=6\nieee80211n=1"
    fi
    if grep -q '^wpa_passphrase=' /etc/hostapd/hostapd.conf 2> /dev/null; then
        PASS=$(grep '^wpa_passphrase=' /etc/hostapd/hostapd.conf | cut -d= -f2)
    else
        PASS=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 16)
    fi
    cat > /etc/hostapd/hostapd.conf << EOF
interface=wlan0
driver=nl80211
ssid=RNS-AndroidAuto
country_code=$COUNTRY
$(echo -e "$BAND")
wmm_enabled=1
auth_algs=1
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
wpa_passphrase=$PASS
EOF
    # wlan0 belongs to hostapd, not NetworkManager
    mkdir -p /etc/NetworkManager/conf.d
    cat > /etc/NetworkManager/conf.d/99-rns-hotspot.conf << 'EOF'
[keyfile]
unmanaged-devices=interface-name:wlan0
EOF
    # Static address + DHCP for the phone from systemd-networkd
    cat > /etc/systemd/network/90-wlan0-hotspot.network << 'EOF'
[Match]
Name=wlan0

[Network]
Address=10.0.0.1/24
DHCPServer=yes

[DHCPServer]
PoolOffset=10
PoolSize=20
EmitDNS=no
EOF
    # 5 GHz channels stay disabled until the kernel knows the country
    sed -i 's/ \?cfg80211.ieee80211_regdom=[A-Z]*//' $CMDLINE
    sed -i "s/$/ cfg80211.ieee80211_regdom=$COUNTRY/" $CMDLINE
    rfkill unblock wlan
    systemctl unmask hostapd
    systemctl enable hostapd systemd-networkd
    green "     Hotspot RNS-AndroidAuto on wlan0 (10.0.0.1) configured. ✅"
}

# Pi 3B+ Bluetooth sits on the UART and only appears as hci0 once hciuart attached it.
# btservice gives up if it starts before that, so make it wait for the adapter.
configure_bluetooth() {
    sed -i '/^dtoverlay=\(pi3-\)\?disable-bt/d' $CONFIG
    sed -i 's/^#\?AutoEnable=.*/AutoEnable=true/' /etc/bluetooth/main.conf
    grep -q '^AutoEnable=' /etc/bluetooth/main.conf || sed -i '/^\[Policy\]/a AutoEnable=true' /etc/bluetooth/main.conf
    sed -i 's/^#\? \?DiscoverableTimeout *=.*/DiscoverableTimeout = 0/' /etc/bluetooth/main.conf
    sed -i 's/^#\? \?AlwaysPairable *=.*/AlwaysPairable = true/' /etc/bluetooth/main.conf
    sed -i 's/^#\? \?JustWorksRepairing *=.*/JustWorksRepairing = always/' /etc/bluetooth/main.conf
    # Classic Bluetooth only (else BlueZ may try LE), and look like car audio to the phone
    sed -i 's/^#\? \?ControllerMode *=.*/ControllerMode = bredr/' /etc/bluetooth/main.conf
    sed -i 's/^#\? \?Class *=.*/Class = 0x200408/' /etc/bluetooth/main.conf
    grep -q '^Class' /etc/bluetooth/main.conf || sed -i '/^\[General\]/a Class = 0x200408' /etc/bluetooth/main.conf

    # The phone only starts wireless Android Auto after a hands-free connection
    # (also carries call audio). bluez-alsa provides HFP/HSP; no A2DP, media goes via Android Auto.
    mkdir -p /etc/systemd/system/bluealsa.service.d
    printf '[Service]\nExecStart=\nExecStart=/usr/bin/bluealsa -S -p hfp-hf -p hsp-hs\n' > /etc/systemd/system/bluealsa.service.d/rns.conf
    systemctl disable bluealsa-aplay.service 2> /dev/null
    # Qt plays to the first ALSA device in the name-hint list; bluealsa's PCM would come
    # before "default" and swallow Android Auto audio
    rm -f /etc/alsa/conf.d/20-bluealsa.conf
    rfkill unblock bluetooth

    cat > /usr/local/bin/rns-bt-ready << 'EOF'
#!/bin/sh
# Wait for hci0, unblock and power it, store its address in openauto.ini
rfkill unblock bluetooth
for i in $(seq 30); do
    [ -e /sys/class/bluetooth/hci0 ] && break
    sleep 1
done
[ -e /sys/class/bluetooth/hci0 ] || { echo "no Bluetooth adapter (hci0)"; exit 1; }
bluetoothctl power on
BT_ADDR=$(hciconfig hci0 2> /dev/null | awk '/BD Address/ {print $3}')
[ -z "$BT_ADDR" ] && BT_ADDR=$(bluetoothctl list | awk '/Controller/ {print $2; exit}')
[ -n "$BT_ADDR" ] && sed -i "s/^AdapterAddress=.*/AdapterAddress=$BT_ADDR/" /etc/openauto/openauto.ini
exit 0
EOF
    chmod +x /usr/local/bin/rns-bt-ready

    mkdir -p /etc/systemd/system/openauto-btservice.service.d
    cat > /etc/systemd/system/openauto-btservice.service.d/rns.conf << 'EOF'
[Unit]
Wants=bluetooth.service hciuart.service
After=bluetooth.service hciuart.service

[Service]
WorkingDirectory=/etc/openauto
ExecStartPre=/usr/local/bin/rns-bt-ready
Restart=always
EOF
    # btservice registers no pairing agent, so without one BlueZ rejects the
    # phone's passkey ("incorrect PIN"). NoInputNoOutput = accept without a PIN.
    cat > /etc/systemd/system/rns-bt-agent.service << 'EOF'
[Unit]
Description=Bluetooth pairing agent (accept phone without PIN)
Requires=bluetooth.service
After=bluetooth.service openauto-btservice.service

[Service]
ExecStartPre=/usr/local/bin/rns-bt-ready
ExecStartPre=/usr/bin/bluetoothctl pairable on
ExecStartPre=/usr/bin/bluetoothctl discoverable on
ExecStart=/usr/bin/bt-agent --capability=NoInputNoOutput
Restart=always
RestartSec=5
KillSignal=SIGUSR1

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    install -m 755 "$SRC/rns-bt-reconnect" /usr/local/bin/rns-bt-reconnect
    cp "$SRC/rns-bt-reconnect.service" /etc/systemd/system/rns-bt-reconnect.service
    systemctl daemon-reload
    systemctl enable bluealsa.service rns-bt-agent.service rns-bt-reconnect.service
    green "     Bluetooth (hciuart, wait for hci0, pairing agent, always discoverable) configured. ✅"
}

configure_openauto() {
    mkdir -p /etc/openauto
    if [ ! -f /etc/openauto/openauto.ini ]; then
        cp "$SRC/openauto.ini" /etc/openauto/openauto.ini
    fi
    BT_ADDR=$(bluetoothctl list 2> /dev/null | awk '/Controller/ {print $2; exit}')
    [ -n "$BT_ADDR" ] && sed -i "s/^AdapterAddress=.*/AdapterAddress=$BT_ADDR/" /etc/openauto/openauto.ini

    # openauto reads openauto.ini from its working directory
    mkdir -p /etc/systemd/system/openauto.service.d
    cat > /etc/systemd/system/openauto.service.d/rns.conf << 'EOF'
[Unit]
After=rnsaa.service hostapd.service pulseaudio-system.service

[Service]
WorkingDirectory=/etc/openauto
Environment="QT_QPA_EGLFS_HIDECURSOR=1"
Environment="PULSE_SERVER=unix:/run/pulse/native"
EOF
    systemctl enable bluetooth hciuart openauto.service openauto-btservice.service
    green "     openauto configured (/etc/openauto/openauto.ini). ✅"
}

install_bridge() {
    echo "Installing MFD button bridge..."
    mkdir -p /opt/rnsaa
    rm -rf /opt/rnsaa/rnsaa
    cp -r "$SRC/rnsaa" /opt/rnsaa/
    [ -f /etc/rnsaa.conf ] || cp "$SRC/rnsaa.conf" /etc/rnsaa.conf
    cp "$SRC/rnsaa.service" /etc/systemd/system/rnsaa.service
    grep -q '^uinput' /etc/modules || echo "uinput" >> /etc/modules
    systemctl daemon-reload
    systemctl enable rnsaa.service
    green "     rnsaa service installed. ✅"
}

rpi_quiet_console() {
    # Nothing but Android Auto on the MFD: no cursor, no login prompt, no boot logo
    grep -q 'vt.global_cursor_default' $CMDLINE || sed -i 's/$/ vt.global_cursor_default=0 consoleblank=0 logo.nologo/' $CMDLINE
    systemctl disable getty@tty1.service &> /dev/null
    if systemctl list-unit-files kodi.service &> /dev/null; then
        systemctl disable --now kodi.service &> /dev/null
        red "     Kodi service disabled (it would fight openauto for the screen)."
    fi
}

green "RNS-MFD1 wireless Android Auto installation 🚀"
check_system
rpi_backup
install_packages
build_openauto

if whiptail --title "MCP2515 crystal" --yes-button " 8 MHz " --no-button " 16 MHz " --yesno "Which crystal is on your MCP2515 module?" 8 50; then
    rpi_add_can0 8000000
else
    rpi_add_can0 16000000
fi

if whiptail --title "Video Output" --yes-button " HDMI " --no-button " JACK " --yesno "Select HDMI-VGA adapter (RGB) or analog composite from the 3.5 mm jack." 10 60; then
    rpi_vga
else
    rpi_composite
fi

rpi_audio_jack
wifi_hotspot
configure_bluetooth
configure_openauto
install_bridge
rpi_quiet_console

green "Done! 🎉"
green "After reboot: MFD -> TV, then on the phone pair Bluetooth with this Pi ($(hostname))."
green "Wi-Fi: RNS-AndroidAuto  password: $PASS   (the phone joins it automatically)"
red "Note: wlan0 is now a hotspot - the Pi no longer joins your home Wi-Fi. Use Ethernet or ssh $user@10.0.0.1"
if whiptail --title "Done" --yesno "Reboot now?" 8 40; then
    reboot
fi
