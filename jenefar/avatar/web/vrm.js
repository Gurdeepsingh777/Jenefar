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
  const camera = new THREE.PerspectiveCamera(24, 1, 0.01, 100);
  camera.position.set(0, 1.18, 5.5);

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
      // Keep the full avatar visible from head to feet. Some VRM fixtures are
      // authored with a T-pose; there is no safe generic way to infer a
      // natural idle arm pose without editing the actual skeleton animation.
      vrm.scene.position.set(0, 0, 0);

      // Natural idle pose for the bundled humanoid VRM.
      // VRM humanoid bones are rotated in local space around their current pose.
      // These values relax the T-pose into a simple arms-down standing pose.
      const humanoid = vrm.humanoid;
      const bone = (name) => humanoid?.getNormalizedBoneNode(name);
      const setEuler = (name, x, y, z) => {
        const node = bone(name);
        if (!node) return;
        node.rotation.x = x;
        node.rotation.y = y;
        node.rotation.z = z;
        node.updateMatrixWorld(true);
      };
      // Premium relaxed pose: shoulders lowered, elbows softened, hands near the waist.
      setEuler("leftUpperArm", 0.08, 0.04, -1.32);
      setEuler("rightUpperArm", 0.08, -0.04, 1.32);
      setEuler("leftLowerArm", 0.34, 0.10, -0.12);
      setEuler("rightLowerArm", 0.34, -0.10, 0.12);
      setEuler("leftHand", 0.02, 0.0, -0.08);
      setEuler("rightHand", 0.02, 0.0, 0.08);
      // Add a subtle jacket/sleeve tint when materials expose a base color.
      try {
        vrm.scene.traverse(node => {
          if (!node.isMesh || !node.material) return;
          const mats = Array.isArray(node.material) ? node.material : [node.material];
          for (const material of mats) {
            if (material.color && material.color.getHex() < 0x555555) {
              material.color.lerp(new THREE.Color(0x0b4f7a), 0.08);
              material.needsUpdate = true;
            }
          }
        });
      } catch (_) {}

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
