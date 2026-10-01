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
  renderer.setClearColor(0x000000, 0);
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 100);
  camera.position.set(0, 1.48, 3.05);
  camera.lookAt(0, 1.32, 0);

  const key = new THREE.DirectionalLight(0xffffff, 3.0);
  key.position.set(1.5, 2.2, 3.5);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x7aa7ff, 1.7);
  fill.position.set(-2, 1, 1);
  scene.add(fill);
  scene.add(new THREE.AmbientLight(0x7d6fff, 0.8));

  let vrm = null;
  let premiumGroup = null;
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

      // Auto-frame the real model instead of assuming a particular VRM unit scale.
      // This prevents tiny/off-center avatars when the source VRM uses different units.
      const bounds = new THREE.Box3().setFromObject(vrm.scene);
      const center = bounds.getCenter(new THREE.Vector3());
      const size = bounds.getSize(new THREE.Vector3());
      const modelHeight = Math.max(size.y, 1.0);
      const modelCenterY = center.y;
      vrm.scene.position.y -= modelCenterY;
      const vFov = THREE.MathUtils.degToRad(camera.fov);
      const fitDistance = (modelHeight * 0.62) / Math.tan(vFov / 2);
      camera.position.set(0, 0, Math.max(2.2, Math.min(8.0, fitDistance)));
      camera.lookAt(0, 0, 0);

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
          const nodeName = String(node.name || "").toLowerCase();
          for (const material of mats) {
            const materialName = String(material.name || "").toLowerCase();
            const key = nodeName + " " + materialName;
            if (key.includes("hair")) {
              material.color?.set(0x120d18);
              material.emissive?.set(0x07040d);
              material.roughness = 0.42;
              material.metalness = 0.06;
            } else if (key.includes("skin") || key.includes("face") || key.includes("body")) {
              material.roughness = 0.5;
              material.metalness = 0.0;
            } else if (key.includes("cloth") || key.includes("dress") || key.includes("outfit") || key.includes("top") || key.includes("shirt") || key.includes("jacket")) {
              material.color?.set(0x101a2b);
              material.roughness = 0.34;
              material.metalness = 0.18;
              material.emissive?.set(0x061c2a);
            } else if (key.includes("shoe") || key.includes("boot")) {
              material.color?.set(0x050b16);
              material.roughness = 0.26;
              material.metalness = 0.5;
            }
            if (material.needsUpdate !== undefined) material.needsUpdate = true;
          }
        });
      } catch (_) {}

      premiumGroup = buildPremiumEnvironment(vrm);
      scene.add(premiumGroup);
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

  function makePremiumMaterial(color, metalness=0.4, roughness=0.3, emissive=0x000000, opacity=1){
    return new THREE.MeshStandardMaterial({
      color, metalness, roughness,
      emissive,
      emissiveIntensity: emissive === 0x000000 ? 0 : 2.2,
      transparent: opacity < 1,
      opacity,
    });
  }

  function addBox(group, size, position, material, radius=0.05){
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material);
    mesh.position.set(...position);
    group.add(mesh);
    return mesh;
  }

  function buildPremiumEnvironment(model){
    const group = new THREE.Group();
    group.name = "JenefarMinimalEnvironment";

    // Keep the VRM visually clean. The uploaded HUD is now the main visual
    // environment; the avatar itself only gets two subtle cyan accents.
    const trimMat = makePremiumMaterial(0x39e6ff, 0.78, 0.16, 0x087f9e);

    const humanoid = model?.humanoid;
    const neck = humanoid?.getNormalizedBoneNode("neck");
    const chest =
      humanoid?.getNormalizedBoneNode("upperChest") ||
      humanoid?.getNormalizedBoneNode("chest");

    if (neck) {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.12, 0.009, 8, 40),
        trimMat
      );
      ring.rotation.x = Math.PI / 2;
      ring.position.set(0, 0.02, 0);
      neck.add(ring);
    }

    if (chest) {
      const core = new THREE.Mesh(
        new THREE.SphereGeometry(0.045, 16, 16),
        trimMat
      );
      core.position.set(0, 0.02, 0.07);
      chest.add(core);
    }

    return group;
  }

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
    if (premiumGroup) {
      premiumGroup.children.forEach(child => {
        if(child.name === "JenefarPremiumParticles"){
          child.rotation.y += 0.0007;
          child.position.y = Math.sin(performance.now() * 0.0006) * 0.025;
        }
      });
    }
    renderer.render(scene, camera);
  }

  window.addEventListener("resize", resize);
  resize();
  loadVRM();
  animate();
}
