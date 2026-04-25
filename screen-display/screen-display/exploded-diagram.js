import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const root = document.getElementById('root');
const explodeButton = document.getElementById('explode-button');
const resetButton = document.getElementById('reset-button');
const cameraKeyframes = [];

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xffffff);
scene.fog = new THREE.Fog(0xf6f7f8, 18, 34);

const camera = new THREE.PerspectiveCamera(34, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(9.5, 7.2, 10.6);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.02;
renderer.physicallyCorrectLights = true;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
root.appendChild(renderer.domElement);
const pmremGenerator = new THREE.PMREMGenerator(renderer);
scene.environment = pmremGenerator.fromScene(new RoomEnvironment(), 0.05).texture;

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.055;
controls.enablePan = false;
controls.minDistance = 6;
controls.maxDistance = 20;
controls.minPolarAngle = Math.PI * 0.16;
controls.maxPolarAngle = Math.PI * 0.48;
controls.target.set(0, 1.4, 0);
controls.update();

const defaultCameraState = {
  position: camera.position.clone(),
  target: controls.target.clone(),
};

const hemiLight = new THREE.HemisphereLight(0xffffff, 0xe7e4de, 1.1);
scene.add(hemiLight);

const keyLight = new THREE.DirectionalLight(0xffffff, 1.25);
keyLight.position.set(7.5, 11, 6.5);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(2048, 2048);
keyLight.shadow.camera.left = -12;
keyLight.shadow.camera.right = 12;
keyLight.shadow.camera.top = 12;
keyLight.shadow.camera.bottom = -12;
keyLight.shadow.camera.near = 0.5;
keyLight.shadow.camera.far = 40;
keyLight.shadow.bias = -0.0002;
keyLight.shadow.normalBias = 0.03;
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0xf2f5f8, 0.35);
fillLight.position.set(-5, 6, -4);
scene.add(fillLight);

const groundPlane = new THREE.Mesh(
  new THREE.PlaneGeometry(40, 40),
  new THREE.ShadowMaterial({
    color: 0x000000,
    opacity: 0.12,
  })
);
groundPlane.rotation.x = -Math.PI / 2;
groundPlane.position.y = 0;
groundPlane.receiveShadow = true;
scene.add(groundPlane);

const groundSurface = new THREE.Mesh(
  new THREE.PlaneGeometry(40, 40),
  new THREE.MeshStandardMaterial({
    color: 0xf2f2f2,
    roughness: 0.9,
    metalness: 0.0,
  })
);
groundSurface.rotation.x = -Math.PI / 2;
groundSurface.position.y = -0.002;
groundSurface.receiveShadow = true;
scene.add(groundSurface);

const contactPlate = new THREE.Mesh(
  new THREE.CircleGeometry(4.5, 96),
  new THREE.MeshBasicMaterial({
    color: 0x000000,
    transparent: true,
    opacity: 0.035,
    depthWrite: false,
  })
);
contactPlate.rotation.x = -Math.PI / 2;
contactPlate.position.y = 0.003;
scene.add(contactPlate);

const loader = new GLTFLoader();
const dracoLoader = new DRACOLoader();
dracoLoader.setDecoderPath('https://www.gstatic.com/draco/v1/decoders/');
loader.setDRACOLoader(dracoLoader);

const diagramRoot = new THREE.Group();
scene.add(diagramRoot);

const explodeFactor = 4.8;
const layerDefinitions = [
  {
    key: 'roof',
    delay: 0.32,
    multiplier: 3.0,
    verticalBoost: 1.8,
  },
  {
    key: 'upper',
    delay: 0.22,
    multiplier: 2.0,
    verticalBoost: 0.9,
  },
  {
    key: 'structure',
    delay: 0.12,
    multiplier: 1.2,
    verticalBoost: -0.18,
  },
  {
    key: 'base',
    delay: 0.06,
    multiplier: 0.8,
    verticalBoost: -0.4,
  },
  {
    key: 'ground',
    delay: 0.0,
    multiplier: 1.5,
    verticalBoost: -1.05,
  },
];

const layerLookup = new Map(layerDefinitions.map((layer) => [layer.key, layer]));
const explodedParts = [];
const activeTweens = new Set();
const keyframeMarkers = [];
let pathLine = null;
let cameraPathGroup = null;
let cameraPathTimeline = null;
let cameraGui = null;
let cameraPathFolder = null;
let pathVisible = true;
let isExploded = true;
let explodedSharedMaterialTemplate = null;
let explodedStorageModelRef = null;

function extractExplodedSharedMaterialTemplate() {
  if (explodedSharedMaterialTemplate || explodedParts.length === 0) {
    return explodedSharedMaterialTemplate;
  }

  const sourcePart = explodedParts.find((part) => !part.mesh.material?.transparent) || explodedParts[0];
  const sourceMaterial = sourcePart?.mesh?.material;
  if (!sourceMaterial) {
    return null;
  }

  explodedSharedMaterialTemplate = sourceMaterial.clone ? sourceMaterial.clone() : sourceMaterial;
  return explodedSharedMaterialTemplate;
}

function setButtonState(exploded) {
  explodeButton.classList.toggle('is-active', exploded);
  resetButton.classList.toggle('is-active', !exploded);
}

function createDiagramMaterial() {
  return new THREE.MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.82,
    metalness: 0.0,
  });
}

function createRoofMaterial() {
  return new THREE.MeshPhysicalMaterial({
    color: 0xffffff,
    transmission: 0.6,
    transparent: true,
    roughness: 0.4,
    metalness: 0,
    thickness: 0.5,
    ior: 1.2,
  });
}

function cloneExplodedSharedPbrMaterial({
  color = '#eaeaea',
  roughness = 0.8,
  glassLike = false,
} = {}) {
  const template = extractExplodedSharedMaterialTemplate();
  let material;

  if (template) {
    material = template.clone ? template.clone() : template;
  } else {
    material = new THREE.MeshPhysicalMaterial({
      color: 0xeaeaea,
      roughness: 0.8,
      metalness: 0.02,
    });
  }

  if (!(material.isMeshStandardMaterial || material.isMeshPhysicalMaterial)) {
    material = new THREE.MeshPhysicalMaterial({
      color: 0xeaeaea,
      roughness: 0.8,
      metalness: 0.02,
    });
  }

  material.color = material.color?.clone ? material.color : new THREE.Color(0xffffff);
  material.color.set(color);
  material.roughness = roughness;
  if ('metalness' in material) {
    material.metalness = Math.max(0.01, material.metalness ?? 0.02);
  }
  if ('envMapIntensity' in material) {
    material.envMapIntensity = material.envMapIntensity ?? 0.6;
  }

  if (glassLike && material.isMeshPhysicalMaterial) {
    material.transparent = true;
    material.opacity = 0.92;
    material.transmission = 0.6;
    material.thickness = 0.5;
    material.ior = 1.2;
  } else {
    material.transparent = false;
    material.opacity = 1;
    if ('transmission' in material) {
      material.transmission = 0;
    }
    if ('thickness' in material) {
      material.thickness = 0;
    }
  }

  material.needsUpdate = true;
  return material;
}

function applySharedMaterialToExplodedStorage(storageModel) {
  if (!storageModel) {
    return;
  }

  storageModel.traverse((child) => {
    if (!child.isMesh) {
      return;
    }

    child.material = cloneExplodedSharedPbrMaterial({
      glassLike: false,
      color: '#eaeaea',
      roughness: 0.8,
    });
    child.castShadow = true;
    child.receiveShadow = true;
  });
}

function inferLayerKey(normalizedY) {
  if (normalizedY > 0.84) {
    return 'roof';
  }
  if (normalizedY > 0.62) {
    return 'upper';
  }
  if (normalizedY > 0.38) {
    return 'structure';
  }
  if (normalizedY > 0.18) {
    return 'base';
  }
  return 'ground';
}

function frameModel(group) {
  const bounds = new THREE.Box3().setFromObject(group);
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z) || 1;
  const scale = 7.2 / maxDim;

  group.scale.setScalar(scale);

  bounds.setFromObject(group);
  const scaledCenter = bounds.getCenter(new THREE.Vector3());
  group.position.set(-scaledCenter.x, -bounds.min.y, -scaledCenter.z);

  bounds.setFromObject(group);
  const scaledSize = bounds.getSize(new THREE.Vector3());
  const scaledCenterFinal = bounds.getCenter(new THREE.Vector3());
  controls.target.copy(scaledCenterFinal.clone().add(new THREE.Vector3(0, scaledSize.y * 0.18, 0)));
  contactPlate.scale.setScalar(Math.max(scaledSize.x, scaledSize.z) * 0.32);
}

function ensureCameraPathGroup() {
  if (cameraPathGroup) {
    return cameraPathGroup;
  }

  cameraPathGroup = new THREE.Group();
  cameraPathGroup.name = 'cameraPathGroup';
  scene.add(cameraPathGroup);
  return cameraPathGroup;
}

function clearCameraPathVisualization() {
  if (pathLine) {
    pathLine.geometry.dispose();
    pathLine.material.dispose();
    pathLine.parent?.remove(pathLine);
    pathLine = null;
  }

  while (keyframeMarkers.length) {
    const marker = keyframeMarkers.pop();
    marker.geometry?.dispose?.();
    marker.material?.dispose?.();
    marker.parent?.remove?.(marker);
  }
}

function updateCameraPathVisibility() {
  if (!cameraPathGroup) {
    return;
  }

  cameraPathGroup.visible = pathVisible && cameraKeyframes.length > 0;
}

function updateCameraPathVisualization() {
  ensureCameraPathGroup();
  clearCameraPathVisualization();

  if (cameraKeyframes.length === 0) {
    updateCameraPathVisibility();
    return;
  }

  const points = cameraKeyframes.map((keyframe) => keyframe.position.clone());
  if (points.length >= 2) {
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
      color: 0xcccccc,
      transparent: true,
      opacity: 0.95,
    });
    pathLine = new THREE.Line(geometry, material);
    cameraPathGroup.add(pathLine);
  }

  cameraKeyframes.forEach((keyframe, index) => {
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(0.08, 18, 18),
      new THREE.MeshStandardMaterial({
        color: index === cameraKeyframes.length - 1 ? 0x2b3440 : 0xbfc6ce,
        roughness: 0.35,
        metalness: 0.0,
      })
    );
    marker.position.copy(keyframe.position);
    cameraPathGroup.add(marker);
    keyframeMarkers.push(marker);
  });

  updateCameraPathVisibility();
}

function stopCameraPathPlayback() {
  if (!cameraPathTimeline) {
    return;
  }

  cameraPathTimeline.kill();
  cameraPathTimeline = null;
  controls.enabled = true;
}

function removeGuiFolder(parentFolder, name) {
  const folder = parentFolder.__folders?.[name];
  if (!folder) {
    return;
  }

  folder.close();
  parentFolder.__ul.removeChild(folder.domElement.parentNode);
  delete parentFolder.__folders[name];
  parentFolder.onResize();
}

function syncKeyframeVectors(keyframe) {
  keyframe.position.set(keyframe.posX, keyframe.posY, keyframe.posZ);
  keyframe.target.set(keyframe.targetX, keyframe.targetY, keyframe.targetZ);
  updateCameraPathVisualization();
}

function rebuildCameraPathGui() {
  if (!cameraPathFolder) {
    return;
  }

  const folderNames = Object.keys(cameraPathFolder.__folders || {});
  folderNames.forEach((name) => {
    removeGuiFolder(cameraPathFolder, name);
  });

  cameraKeyframes.forEach((keyframe, index) => {
    const folder = cameraPathFolder.addFolder(`Keyframe ${index + 1}`);
    folder.add(keyframe, 'posX', -20, 20, 0.01).name('Cam X').onChange(() => syncKeyframeVectors(keyframe));
    folder.add(keyframe, 'posY', -20, 20, 0.01).name('Cam Y').onChange(() => syncKeyframeVectors(keyframe));
    folder.add(keyframe, 'posZ', -20, 20, 0.01).name('Cam Z').onChange(() => syncKeyframeVectors(keyframe));
    folder.add(keyframe, 'targetX', -20, 20, 0.01).name('Target X').onChange(() => syncKeyframeVectors(keyframe));
    folder.add(keyframe, 'targetY', -20, 20, 0.01).name('Target Y').onChange(() => syncKeyframeVectors(keyframe));
    folder.add(keyframe, 'targetZ', -20, 20, 0.01).name('Target Z').onChange(() => syncKeyframeVectors(keyframe));
    folder.add(keyframe, 'duration', 0.2, 8, 0.1).name('Duration');
  });
}

function addCameraKeyframe() {
  const keyframe = {
    position: camera.position.clone(),
    target: controls.target.clone(),
    duration: 2,
    posX: camera.position.x,
    posY: camera.position.y,
    posZ: camera.position.z,
    targetX: controls.target.x,
    targetY: controls.target.y,
    targetZ: controls.target.z,
  };

  cameraKeyframes.push(keyframe);
  updateCameraPathVisualization();
  rebuildCameraPathGui();
}

function playCameraPath() {
  if (cameraKeyframes.length === 0) {
    return;
  }

  stopCameraPathPlayback();
  controls.enabled = false;

  cameraPathTimeline = window.gsap.timeline({
    onComplete: () => {
      cameraPathTimeline = null;
      controls.enabled = true;
    },
    onInterrupt: () => {
      cameraPathTimeline = null;
      controls.enabled = true;
    },
  });

  let timelineOffset = 0;
  cameraKeyframes.forEach((keyframe) => {
    cameraPathTimeline.to(camera.position, {
      x: keyframe.position.x,
      y: keyframe.position.y,
      z: keyframe.position.z,
      duration: keyframe.duration,
      ease: 'power2.inOut',
      onUpdate: () => controls.update(),
    }, timelineOffset);

    cameraPathTimeline.to(controls.target, {
      x: keyframe.target.x,
      y: keyframe.target.y,
      z: keyframe.target.z,
      duration: keyframe.duration,
      ease: 'power2.inOut',
      onUpdate: () => controls.update(),
    }, timelineOffset);

    timelineOffset += keyframe.duration;
  });
}

function resetCameraView() {
  stopCameraPathPlayback();
  camera.position.copy(defaultCameraState.position);
  controls.target.copy(defaultCameraState.target);
  controls.update();
}

function togglePathVisibility() {
  pathVisible = !pathVisible;
  updateCameraPathVisibility();
}

function setupCameraGui() {
  if (!window.dat || cameraGui) {
    return;
  }

  cameraGui = new window.dat.GUI({ name: 'Camera Path Designer' });
  cameraGui.width = 320;

  const actions = {
    addKeyframe: addCameraKeyframe,
    playAnimation: playCameraPath,
    resetCamera: resetCameraView,
    togglePathVisibility,
  };

  cameraGui.add(actions, 'addKeyframe').name('Add Keyframe');
  cameraGui.add(actions, 'playAnimation').name('Play Animation');
  cameraGui.add(actions, 'resetCamera').name('Reset Camera');
  cameraGui.add(actions, 'togglePathVisibility').name('Toggle Path');
  cameraPathFolder = cameraGui.addFolder('Keyframes');
  cameraPathFolder.open();
}

function createGuideLine(parent, originalPosition, targetPosition) {
  const geometry = new THREE.BufferGeometry().setFromPoints([
    originalPosition.clone(),
    targetPosition.clone(),
  ]);
  const material = new THREE.LineDashedMaterial({
    color: 0xb7bec7,
    dashSize: 0.09,
    gapSize: 0.06,
    transparent: true,
    opacity: 0.72,
    depthWrite: false,
  });
  const line = new THREE.Line(geometry, material);
  line.computeLineDistances();
  line.visible = false;
  parent.add(line);
  return line;
}

function prepareExplodedParts(model) {
  const meshCenters = [];

  model.traverse((child) => {
    if (!child.isMesh) {
      return;
    }

    child.userData.originalPosition = child.position.clone();
    child.castShadow = true;
    child.receiveShadow = true;

    const bounds = new THREE.Box3().setFromObject(child);
    const center = bounds.getCenter(new THREE.Vector3());
    meshCenters.push({ child, center, centerY: center.y });
  });

  if (meshCenters.length === 0) {
    return;
  }

  const modelBounds = new THREE.Box3().setFromObject(model);
  const modelCenterWorld = modelBounds.getCenter(new THREE.Vector3());
  const minY = Math.min(...meshCenters.map((entry) => entry.centerY));
  const maxY = Math.max(...meshCenters.map((entry) => entry.centerY));
  const rangeY = Math.max(maxY - minY, 0.001);

  meshCenters.forEach(({ child, center, centerY }) => {
    const normalizedY = (centerY - minY) / rangeY;
    const layerKey = inferLayerKey(normalizedY);
    const layer = layerLookup.get(layerKey);
    const localModelCenter = child.parent.worldToLocal(modelCenterWorld.clone());
    const radialDirection = child.position.clone().sub(localModelCenter);
    if (radialDirection.lengthSq() < 1e-6) {
      radialDirection.set(0, 1, 0);
    } else {
      radialDirection.normalize();
    }

    const meshBounds = new THREE.Box3().setFromObject(child);
    const meshSize = meshBounds.getSize(new THREE.Vector3());
    const meshDistance = Math.max(meshSize.length(), 0.45);
    const baseOffset = radialDirection.multiplyScalar(meshDistance * explodeFactor * layer.multiplier);
    baseOffset.y += layer.verticalBoost;

    const originalPosition = child.userData.originalPosition.clone();
    const targetPosition = originalPosition.clone().add(baseOffset);
    const guideLine = createGuideLine(child.parent, originalPosition, targetPosition);
    const looksLikeRoof = /roof/i.test(child.name) || layerKey === 'roof';

    child.material = looksLikeRoof ? createRoofMaterial() : createDiagramMaterial();

    explodedParts.push({
      mesh: child,
      layerKey,
      originalPosition,
      targetPosition,
      guideLine,
      delay: layer.delay,
      duration: 1.5,
    });
  });

  extractExplodedSharedMaterialTemplate();
  applySharedMaterialToExplodedStorage(explodedStorageModelRef);
}

function setExplodedState(exploded, immediate = false) {
  isExploded = exploded;
  setButtonState(exploded);
  activeTweens.forEach((tween) => tween.kill());
  activeTweens.clear();

  if (immediate) {
    explodedParts.forEach((part) => {
      part.mesh.position.copy(exploded ? part.targetPosition : part.originalPosition);
      part.guideLine.visible = exploded;
      part.guideLine.material.opacity = exploded ? 0.72 : 0;
    });
    return;
  }

  explodedParts.forEach((part) => {
    const destination = exploded ? part.targetPosition : part.originalPosition;
    part.guideLine.visible = true;

    const positionTween = window.gsap.to(part.mesh.position, {
      x: destination.x,
      y: destination.y,
      z: destination.z,
      duration: part.duration,
      delay: part.delay,
      ease: 'power3.out',
      onComplete: () => {
        activeTweens.delete(positionTween);
      },
    });

    const guideTween = window.gsap.to(part.guideLine.material, {
      opacity: exploded ? 0.72 : 0,
      duration: 0.7,
      delay: part.delay * 0.85,
      ease: 'power2.out',
      onUpdate: () => {
        part.guideLine.visible = part.guideLine.material.opacity > 0.02;
      },
      onComplete: () => {
        part.guideLine.visible = exploded;
        activeTweens.delete(guideTween);
      },
    });

    activeTweens.add(positionTween);
    activeTweens.add(guideTween);
  });
}

loader.load(
  './models/Untitled-2.glb',
  (gltf) => {
    const model = gltf.scene;
    model.name = 'explodedHouseModel';
    diagramRoot.add(model);

    frameModel(model);
    defaultCameraState.position.copy(camera.position);
    defaultCameraState.target.copy(controls.target);
    prepareExplodedParts(model);
    setExplodedState(false, true);
    setupCameraGui();
    window.setTimeout(() => {
      setExplodedState(true, false);
    }, 260);
  },
  undefined,
  (error) => {
    console.error('Exploded diagram GLB load error:', error);
  }
);

explodeButton.addEventListener('click', () => {
  stopCameraPathPlayback();
  setExplodedState(true);
});

resetButton.addEventListener('click', () => {
  stopCameraPathPlayback();
  setExplodedState(false);
});

function animate() {
  controls.update();
  renderer.render(scene, camera);
}

renderer.setAnimationLoop(animate);

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
