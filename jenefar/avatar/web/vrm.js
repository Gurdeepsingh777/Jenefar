import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";

const canvas = document.getElementById("vrm-canvas");
const status = document.getElementById("vrm-status");

if (canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(28, 1, 0.01, 100);
  camera.position.set(0, 1.35, 3.1);

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
      vrm.scene.rotation.y = Math.PI;
      scene.add(vrm.scene);
      document.body.classList.add("vrm-loaded");
      if (status) status.textContent = "VRM AVATAR";
    } catch (_error) {
      if (status) status.textContent = "PROCEDURAL AVATAR";
    }
  }

  window.addEventListener("jenefar-avatar-event", event => {
    const data = event.detail || {};
    targetLevel = Number(data.level || 0);
    targetEmotion = data.emotion || "neutral";
  });

  function setExpression(name, value) {
    if (!vrm?.expressionManager) return;
    try {
      vrm.expressionManager.setValue(name, value);
    } catch (_) {}
  }

  function animate() {
    requestAnimationFrame(animate);
    mouthLevel += (targetLevel - mouthLevel) * 0.18;
    if (vrm?.expressionManager) {
      setExpression("aa", Math.min(1, mouthLevel));
      setExpression("blink", 0);
      if (targetEmotion === "happy") setExpression("happy", 0.45);
      else if (targetEmotion === "sad") setExpression("sad", 0.35);
      else if (targetEmotion === "alert") setExpression("angry", 0.28);
      else if (targetEmotion === "focused") setExpression("relaxed", 0.18);
    }
    if (vrm) {
      vrm.scene.position.y = Math.sin(performance.now() * 0.0012) * 0.008;
      vrm.scene.rotation.y = Math.PI + Math.sin(performance.now() * 0.0004) * 0.025;
      vrm.update(1 / 60);
    }
    renderer.render(scene, camera);
  }

  window.addEventListener("resize", resize);
  resize();
  loadVRM();
  animate();
}
