# Après un flash déclenché par le reset 1200 bauds, l'ESP32-S3 garde le drapeau
# FORCE_DOWNLOAD_BOOT (RTC_CNTL_OPTION1_REG) et redémarre en mode flash.
# On l'efface puis on redémarre pour lancer le firmware.
Import("env")


def clear_force_download(source, target, env):
    port = env.subst("$UPLOAD_PORT")
    env.Execute(
        f'"$PYTHONEXE" "$UPLOADER" --chip esp32s3 --port {port} '
        "--after hard_reset write_mem 0x6000812C 0 0x1"
    )


env.AddPostAction("upload", clear_force_download)
