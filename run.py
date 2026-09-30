                avatar_model = setup_avatar_asset()
                print(f"[JENEFAR] VRM avatar ready: {avatar_model}")
            except Exception as exc:
                print(
                    "[JENEFAR] VRM provisioning skipped: "
                    f"{type(exc).__name__}: {exc}"
                )
        avatar_server = AvatarServer(
            avatar,
            port=args.avatar_port,
            vrm_path=avatar_model if avatar_model.is_file() else None,
            tool_broker=orchestrator.tool_broker,
            voice_handler=browser_voice.handle_text if browser_voice_enabled else None,
        )
        avatar_server.start()

        runtime_url = avatar_server.url
        print(f"[JENEFAR] Avatar UI: {runtime_url}")
        print(f"[JENEFAR] Avatar health: {runtime_url}health")
        print("[JENEFAR] Opening Jenefar UI in the default browser...")
        try:
            webbrowser.open(runtime_url)
        except Exception:
            print(f"[JENEFAR] Open this URL manually: {runtime_url}")

        audio_status = ProviderVoiceRuntime.audio_status()
        print(
            "[JENEFAR] One-command runtime: avatar UI + continuous voice + "
            "multi-agent orchestrator + memory + tools + diagnostics."
        )
        if audio_status["stt"]:
            stt = audio_status["stt"]
            tts = audio_status["tts"]
            print(
                f"[JENEFAR] Voice providers: "
                f"STT={stt['provider']}/{stt['model']} "
                f"fallback={','.join(stt.get('fallback', [])) or 'none'}; "
                f"TTS={tts['provider']}/{tts['model']} "
                f"fallback={','.join(tts.get('fallback', [])) or 'none'}"
            )
        else:
            print("[JENEFAR] No online STT provider configured; using terminal text mode.")

        try:
            if browser_voice_enabled:
                print("[JENEFAR] Browser microphone voice: ENABLED.")
                print("[JENEFAR] Chrome/Chromium will ask for microphone permission in the avatar UI.")
                print("[JENEFAR] Python sounddevice voice is fallback mode: set JENEFAR_BROWSER_VOICE=0 to use it.")
                if not audio_status["tts"]:
                    print("[JENEFAR] No Python TTS configured; browser speech synthesis will be used as UI fallback.")
                threading.Event().wait()
            else:
                try:
                    import sounddevice  # noqa: F401
                except ImportError as exc:
                    print(f"[JENEFAR] Voice dependency missing: sounddevice ({exc}).")
                    print("[JENEFAR] The avatar UI is still available.")
                    orchestrator.run()
                else:
                    if audio_status["stt"]:
                        ContinuousVoiceRuntime(orchestrator, avatar=avatar).run()