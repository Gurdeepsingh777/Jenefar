import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";

const canvas = document.getElementById("vrm-canvas");
const status = document.getElementById("vrm-status");
function setVRMStatus(text, failed=false) {
  if (!status) return;
  status.textContent = text;
  status.dataset.error = failed ? "true" : "false";
}

if (canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(22, 1, 0.01, 100);
  camera.position.set(0, 1.18, 4.6);

  const key = new THREE.DirectionalLight(0xffffff, 3.0);
  key.position.set(1.5, 2.2, 3.5);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x7aa7ff, 1.7);
  fill.position.set(-2, 1, 1);
  scene.add(fill);
  scene.add(new THREE.AmbientLight(0x7d6fff, 0.8));

  let vrm = null;
  let targetLevel = 0;
  let mouthLevel = 0;
  let targetEmotion = "neutral";
  let speechText = "";
  let lastBlink = performance.now();

  function resize() {
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  async function loadVRM() {
    const loader = new GLTFLoader();
    loader.register(parser => new VRMLoaderPlugin(parser));

    try {
      const gltf = await loader.loadAsync("/avatar.vrm");
      vrm = gltf.userData.vrm;
      VRMUtils.rotateVRM0(vrm);
      // The bundled VRM sample already faces the standard camera direction.
      // The previous extra PI rotation showed its back to the user.
      vrm.scene.rotation.y = 0;
      vrm.scene.position.y = 0;
      scene.add(vrm.scene);
      document.body.classList.add("vrm-loaded");
      setVRMStatus("VRM AVATAR");
    } catch (error) {
      console.error("[JENEFAR] VRM load failed", error);
      setVRMStatus("VRM ERROR", true);
      document.body.classList.add("vrm-error");
    }
  }

  window.addEventListener("jenefar-avatar-event", event => {
    const data = event.detail || {};
    targetLevel = Number(data.level || 0);
    targetEmotion = data.emotion || "neutral";
    if (typeof data.text === "string" && data.text) speechText = data.text;
  });

  function setExpression(name, value) {
    if (!vrm?.expressionManager) return;
    try {
      vrm.expressionManager.setValue(name, value);
    } catch (_) {}
  }

  function phonemeForText(text, phase) {
    const vowels = [...text.toLowerCase()].filter(ch => "aeiou".includes(ch));
    if (!vowels.length) return "aa";
    const vowel = vowels[Math.floor(phase % vowels.length)];
    return ({a: "aa", e: "ee", i: "ih", o: "oh", u: "ou"})[vowel] || "aa";
  }

  function animate() {
    requestAnimationFrame(animate);
    mouthLevel += (targetLevel - mouthLevel) * 0.18;
    if (vrm?.expressionManager) {
      const now = performance.now();
      const phase = now * 0.018;
      const phoneme = phonemeForText(speechText, phase / 12);
      for (const name of ["aa", "ee", "ih", "oh", "ou"]) setExpression(name, 0);
      if (mouthLevel > 0.06) setExpression(phoneme, Math.min(1, mouthLevel));
      if (mouthLevel <= 0.06 && now - lastBlink > 2800) {
        setExpression("blink", 0.95);
        lastBlink = now;
      } else if (mouthLevel <= 0.06) {
        setExpression("blink", 0);
      }
      if (targetEmotion === "happy") setExpression("happy", 0.45);
      else if (targetEmotion === "sad") setExpression("sad", 0.35);
      else if (targetEmotion === "alert") setExpression("angry", 0.28);
      else if (targetEmotion === "focused") setExpression("relaxed", 0.18);
    }
    if (vrm) {
      vrm.scene.position.y = Math.sin(performance.now() * 0.0012) * 0.004;
      vrm.scene.rotation.y = Math.sin(performance.now() * 0.0004) * 0.025;
      vrm.update(1 / 60);
    }
    renderer.render(scene, camera);
  }

  window.addEventListener("resize", resize);
  resize();
  loadVRM();
  animate();
}
