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
  const camera = new THREE.PerspectiveCamera(24, 1, 0.01, 100);
  camera.position.set(0, 1.55, 4.55);
  camera.lookAt(0, 1.38, 0);

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
              material.color?.set(0xf0f5fb);
              material.roughness = 0.34;
              material.metalness = 0.18;
              material.emissive?.set(0x04111c);
            } else if (key.includes("shoe") || key.includes("boot")) {
              material.color?.set(0x101927);
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
    group.name = "JenefarPremiumEnvironment";

    const chairMat = makePremiumMaterial(0x070d18, 0.72, 0.22, 0x071a2b);
    const trimMat = makePremiumMaterial(0x3cecff, 0.78, 0.18, 0x0a7ea0);
    const softMat = makePremiumMaterial(0x16233b, 0.28, 0.55);

    // Futuristic chair silhouette, positioned behind the avatar.
    addBox(group, [2.25, 2.35, 0.30], [0, 1.85, -0.72], chairMat);
    addBox(group, [2.45, 0.22, 1.75], [0, 0.68, -0.25], softMat);
    addBox(group, [0.18, 1.00, 1.25], [-1.05, 1.12, -0.22], chairMat);
    addBox(group, [0.18, 1.00, 1.25], [1.05, 1.12, -0.22], chairMat);

    const backGlow = new THREE.Mesh(
      new THREE.BoxGeometry(2.35, 1.72, 0.02),
      makePremiumMaterial(0x1c7ec4, 0.20, 0.62, 0x0c5f83, 0.05)
    );
    backGlow.position.set(0, 1.63, -0.545);
    backGlow.visible = false;
    group.add(backGlow);

    const base = new THREE.Mesh(
      new THREE.CylinderGeometry(0.55, 0.72, 0.08, 48),
      chairMat
    );
    base.position.set(0, 0.48, -0.10);
    group.add(base);

    // A thin luminous collar/chest core follows the humanoid rig.
    const humanoid = model?.humanoid;
    const neck = humanoid?.getNormalizedBoneNode("neck");
    const chest = humanoid?.getNormalizedBoneNode("upperChest") || humanoid?.getNormalizedBoneNode("chest");
    if(neck){
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.14, 0.012, 8, 48), trimMat);
      ring.rotation.x = Math.PI / 2;
      ring.position.set(0, 0.02, 0);
      neck.add(ring);
    }
    if(chest){
      const core = new THREE.Mesh(new THREE.SphereGeometry(0.055, 20, 20), trimMat);
      core.position.set(0, 0.02, 0.08);
      chest.add(core);
    }

    // Holographic particle field around the seated command position.
    const count = 220;
    const positions = new Float32Array(count * 3);
    for(let i=0;i<count;i++){
      const radius = 1.4 + Math.random() * 2.6;
      const angle = Math.random() * Math.PI * 2;
      positions[i*3] = Math.cos(angle) * radius;
      positions[i*3+1] = 0.55 + Math.random() * 2.8;
      positions[i*3+2] = -0.2 + Math.sin(angle) * radius * 0.42;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions,3));
    const points = new THREE.Points(
      geometry,
      new THREE.PointsMaterial({color:0x65e8ff,size:0.022,transparent:true,opacity:0.55})
    );
    points.name = "JenefarPremiumParticles";
    group.add(points);

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
