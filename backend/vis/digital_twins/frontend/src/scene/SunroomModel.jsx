import React, { useMemo, useRef, useEffect, useState } from 'react';
import { Html } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useTwinStore } from '../store/useTwinStore.js';
import { CharacterManager } from './Character.jsx';
import { buildNavigationConfig } from './pathfinding.js';

const GROUND_Y = 0.12;
const MEETING_ZONE_SHIFT_X = 0.65;

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

function cctToColor(cct = 4200) {
  if (cct <= 3200) return '#ffd395';
  if (cct <= 4200) return '#ffe7bc';
  if (cct <= 5200) return '#f2f0ff';
  return '#dfe8ff';
}

function domainColor(domain) {
  return {
    lighting: '#f8c24a',
    display: '#55b4ff',
    access: '#f46d6d',
    environment: '#7cc97d',
    climate: '#70d4c8',
    sensing: '#b8a8ff',
    robot: '#888888'
  }[domain] || '#ffffff';
}

function Beam({ start, end, radius = 0.05, color = '#f5f0e8' }) {
  const data = useMemo(() => {
    const startVec = new THREE.Vector3(...start);
    const endVec = new THREE.Vector3(...end);
    const direction = endVec.clone().sub(startVec);
    const length = direction.length();
    const midpoint = startVec.clone().add(endVec).multiplyScalar(0.5);
    const quaternion = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      direction.clone().normalize()
    );
    return { midpoint, quaternion, length };
  }, [start, end]);

  return (
    <mesh position={data.midpoint} quaternion={data.quaternion} castShadow receiveShadow>
      <cylinderGeometry args={[radius, radius, data.length, 10]} />
      <meshStandardMaterial color={color} roughness={0.35} metalness={0.08} />
    </mesh>
  );
}

function CurvedShell({
  profile,
  depth,
  thickness = 0.08,
  position = [0, 0, 0],
  color = '#f7f4ea',
  opacity = 0.3
}) {
  const geometry = useMemo(() => {
    const p0 = new THREE.Vector2(profile[0][0], profile[0][1]);
    const p1 = new THREE.Vector2(profile[1][0], profile[1][1]);
    const p2 = new THREE.Vector2(profile[2][0], profile[2][1]);

    const sampleQuadratic = (t) => {
      const oneMinus = 1 - t;
      const x = oneMinus * oneMinus * p0.x + 2 * oneMinus * t * p1.x + t * t * p2.x;
      const y = oneMinus * oneMinus * p0.y + 2 * oneMinus * t * p1.y + t * t * p2.y;
      return new THREE.Vector2(x, y);
    };

    const samples = [];
    for (let i = 0; i <= 24; i += 1) samples.push(sampleQuadratic(i / 24));

    const shape = new THREE.Shape();
    shape.moveTo(samples[0].x, samples[0].y);
    samples.slice(1).forEach((point) => shape.lineTo(point.x, point.y));
    for (let i = samples.length - 1; i >= 0; i -= 1) {
      shape.lineTo(samples[i].x, samples[i].y - thickness);
    }
    shape.closePath();

    const geom = new THREE.ExtrudeGeometry(shape, {
      steps: 1,
      depth,
      bevelEnabled: false
    });
    geom.center();
    return geom;
  }, [profile, depth, thickness]);

  return (
    <mesh
      geometry={geometry}
      rotation={[0, -Math.PI / 2, 0]}
      position={position}
      castShadow
      receiveShadow
    >
      <meshStandardMaterial
        color={color}
        transparent
        opacity={opacity}
        roughness={0.22}
        metalness={0.06}
      />
    </mesh>
  );
}

function Marker({ position, label, color, active, onClick }) {
  return (
    <group
      position={position}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
    >
      <mesh castShadow>
        <sphereGeometry args={[active ? 0.12 : 0.08, 18, 18]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={active ? 0.8 : 0.2}
        />
      </mesh>
      {active ? (
        <Html distanceFactor={10} position={[0, 0.35, 0]} transform>
          <div className="marker-label">{label}</div>
        </Html>
      ) : null}
    </group>
  );
}

function deviceMapFromList(devices) {
  return devices.reduce((acc, device) => {
    acc[device.id] = device;
    return acc;
  }, {});
}

function Chair({ position, rotation = [0, 0, 0], scale = 0.9 }) {
  return (
    <group position={position} rotation={rotation} scale={scale}>
      <mesh castShadow position={[0, 0.42, 0]}>
        <boxGeometry args={[0.58, 0.06, 0.58]} />
        <meshStandardMaterial color="#1f2328" roughness={0.55} />
      </mesh>
      <mesh castShadow position={[0, 0.78, -0.22]}>
        <boxGeometry args={[0.58, 0.7, 0.06]} />
        <meshStandardMaterial color="#1f2328" roughness={0.55} />
      </mesh>
      {[
        [-0.22, 0.21, -0.22],
        [0.22, 0.21, -0.22],
        [-0.22, 0.21, 0.22],
        [0.22, 0.21, 0.22]
      ].map((leg, index) => (
        <mesh key={index} castShadow position={leg}>
          <boxGeometry args={[0.05, 0.42, 0.05]} />
          <meshStandardMaterial color="#9ea3a8" metalness={0.25} roughness={0.45} />
        </mesh>
      ))}
    </group>
  );
}

function WorkDesk({ position }) {
  return (
    <group position={position}>
      <mesh castShadow receiveShadow position={[0, 0.74, 0]}>
        <boxGeometry args={[0.52, 0.08, 1.25]} />
        <meshStandardMaterial color="#4a74c9" roughness={0.55} />
      </mesh>
      {[
        [-0.22, 0.37, -0.52],
        [0.22, 0.37, -0.52],
        [-0.22, 0.37, 0.52],
        [0.22, 0.37, 0.52]
      ].map((leg, index) => (
        <mesh key={index} castShadow position={leg}>
          <boxGeometry args={[0.06, 0.74, 0.06]} />
          <meshStandardMaterial color="#8d939a" metalness={0.22} roughness={0.5} />
        </mesh>
      ))}
    </group>
  );
}

function getRestZoneWallSegments(center, size, height = 1.8, wallThickness = 0.12, gapWidth = 0.9) {
  const [cx, , cz] = center;
  const [sx, , sz] = size;

  const leftX = cx - sx / 2;
  const rightX = cx + sx / 2;
  const topZ = cz - sz / 2;
  const bottomZ = cz + sz / 2;

  const doorGapCenterZ = bottomZ - 0.45;
  const gapStart = doorGapCenterZ - gapWidth / 2;
  const gapEnd = doorGapCenterZ + gapWidth / 2;

  return [
    {
      key: 'top',
      position: [cx, height / 2, topZ],
      size: [sx, height, wallThickness]
    },
    {
      key: 'right',
      position: [rightX, height / 2, cz],
      size: [wallThickness, height, sz]
    },
    {
      key: 'bottom',
      position: [cx, height / 2, bottomZ],
      size: [sx, height, wallThickness]
    },
    {
      key: 'left-top',
      position: [leftX, height / 2, (topZ + gapStart) / 2],
      size: [wallThickness, height, Math.max(0.01, gapStart - topZ)]
    },
    {
      key: 'left-bottom',
      position: [leftX, height / 2, (gapEnd + bottomZ) / 2],
      size: [wallThickness, height, Math.max(0.01, bottomZ - gapEnd)]
    }
  ];
}

function rectFromCenter([x, , z], [sizeX, , sizeZ]) {
  return {
    minX: x - sizeX / 2,
    maxX: x + sizeX / 2,
    minZ: z - sizeZ / 2,
    maxZ: z + sizeZ / 2
  };
}

function getRestZoneWallObstacles(center, size, height = 1.8, wallThickness = 0.12, gapWidth = 0.9) {
  return getRestZoneWallSegments(center, size, height, wallThickness, gapWidth)
    .map((segment) => rectFromCenter(segment.position, segment.size))
    .filter((rect) => rect.minX < rect.maxX && rect.minZ < rect.maxZ);
}

function getWorkDeskObstacles(deskPositions) {
  return deskPositions.map((position) => rectFromCenter([position[0], 0, position[2]], [0.52, 0, 1.25]));
}

function getMeetingTableObstacle(center = [2.3, 0, -0.05], size = [1.55, 0, 2.6]) {
  return rectFromCenter([center[0], 0, center[2]], [size[0], 0, size[2]]);
}

function getRobotOffset(status = 'docked', progress = 0) {
  if (status !== 'running') return 0;
  return Math.sin(progress * Math.PI * 2) * 0.45;
}

function getRobotObstacle(position, status = 'docked', progress = 0) {
  const offset = getRobotOffset(status, progress);
  const sweep = status === 'running' ? 0.9 : 0;
  const x = position[0] + offset;
  return rectFromCenter([x, 0, position[2]], [1.18 + sweep, 0, 0.82]);
}

function RestZonePartition({ center, size, height = 1.8, wallThickness = 0.12, gapWidth = 0.9 }) {
  const wallSegments = getRestZoneWallSegments(center, size, height, wallThickness, gapWidth);

  return (
    <group>
      {wallSegments.map((segment) => (
        <mesh key={segment.key} castShadow receiveShadow position={segment.position}>
          <boxGeometry args={segment.size} />
          <meshStandardMaterial color="#23272c" roughness={0.84} />
        </mesh>
      ))}
    </group>
  );
}

function Laptop({ position, rotation = [0, 0, 0], accent = '#68b8ff', active = true }) {
  return (
    <group position={position} rotation={rotation}>
      <mesh castShadow receiveShadow position={[0, 0.02, 0]}>
        <boxGeometry args={[0.34, 0.028, 0.24]} />
        <meshStandardMaterial color="#596270" roughness={0.4} metalness={0.38} />
      </mesh>
      <group position={[0, 0.034, -0.102]} rotation={[-1.16, 0, 0]}>
        <mesh castShadow>
          <boxGeometry args={[0.32, 0.2, 0.018]} />
          <meshStandardMaterial color="#2c3139" roughness={0.28} metalness={0.2} />
        </mesh>
        <mesh position={[0, 0, 0.01]}>
          <planeGeometry args={[0.27, 0.16]} />
          <meshStandardMaterial
            color={active ? accent : '#11151a'}
            emissive={active ? accent : '#000000'}
            emissiveIntensity={active ? 0.55 : 0}
          />
        </mesh>
      </group>
    </group>
  );
}

function ScreenDisplay({
  position,
  rotation = [0, 0, 0],
  size = [2.2, 1.4, 0.1],
  mode = 'dashboard',
  title = 'Workspace Twin',
  subtitle = '',
  doubleSided = false
}) {
  const isMeeting = mode === 'meeting';
  const isOff = mode === 'off';
  const shellColor = isMeeting ? '#253244' : '#263546';
  const screenColor = isOff ? '#101216' : isMeeting ? '#143b5b' : '#0d3b5e';
  const accent = isOff ? '#33404a' : isMeeting ? '#5bc0ff' : '#68b8ff';
  const contentBars = isMeeting
    ? [0.92, 0.74, 0.58, 0.66]
    : [0.84, 0.68, 0.48, 0.76];
  const faces = doubleSided ? [1, -1] : [1];

  return (
    <group position={position} rotation={rotation}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={size} />
        <meshStandardMaterial color={shellColor} roughness={0.38} metalness={0.18} />
      </mesh>
      {faces.map((direction) => {
        const faceOffset = (size[2] / 2 + 0.008) * direction;
        const contentOffset = (size[2] / 2 + 0.012) * direction;
        const faceRotation = direction < 0 ? [0, Math.PI, 0] : [0, 0, 0];

        return (
          <group key={direction}>
            <mesh position={[0, 0, faceOffset]} rotation={faceRotation}>
              <planeGeometry args={[size[0] * 0.88, size[1] * 0.78]} />
              <meshStandardMaterial color={screenColor} emissive={screenColor} emissiveIntensity={isOff ? 0 : 0.2} />
            </mesh>
            {!isOff ? (
              <group position={[0, 0, contentOffset]} rotation={faceRotation}>
                <mesh position={[0, size[1] * 0.22, 0.001]}>
                  <planeGeometry args={[size[0] * 0.76, size[1] * 0.09]} />
                  <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={0.35} />
                </mesh>
                {contentBars.map((scale, index) => (
                  <mesh key={index} position={[-size[0] * 0.12, size[1] * (0.07 - index * 0.12), 0.001 + index * 0.0002]}>
                    <planeGeometry args={[size[0] * 0.54 * scale, size[1] * 0.05]} />
                    <meshStandardMaterial color={index === 0 ? '#f2fbff' : '#84d7ff'} emissive={accent} emissiveIntensity={0.14} />
                  </mesh>
                ))}
                <mesh position={[size[0] * 0.24, -size[1] * 0.02, 0.001]}>
                  <planeGeometry args={[size[0] * 0.22, size[1] * 0.34]} />
                  <meshStandardMaterial color={isMeeting ? '#1b7bb8' : '#1d6592'} emissive={accent} emissiveIntensity={0.18} />
                </mesh>
                <mesh position={[size[0] * 0.24, -size[1] * 0.02, 0.002]}>
                  <ringGeometry args={[size[0] * 0.035, size[0] * 0.065, 24]} />
                  <meshStandardMaterial color="#d6f4ff" emissive="#8bddff" emissiveIntensity={0.3} />
                </mesh>
              </group>
            ) : null}
            <Html distanceFactor={10} position={[0, 0, (size[2] / 2 + 0.02) * direction]} rotation={faceRotation} transform>
              <div
                style={{
                  width: Math.max(120, size[0] * 90),
                  color: isOff ? '#76838d' : '#eff8ff',
                  fontSize: 12,
                  fontWeight: 600,
                  textAlign: 'left',
                  pointerEvents: 'none',
                  textShadow: isOff ? 'none' : '0 0 16px rgba(15,90,140,0.45)'
                }}
              >
                <div>{title}</div>
                <div style={{ marginTop: 6, opacity: 0.8, fontSize: 10, fontWeight: 500 }}>{subtitle}</div>
              </div>
            </Html>
          </group>
        );
      })}
    </group>
  );
}

function Robot({ position, status = 'docked', progress = 0 }) {
  const group = useRef();

  useFrame(() => {
    if (!group.current) return;
    const offset = getRobotOffset(status, progress);
    group.current.position.x = position[0] + offset;
    group.current.rotation.y = status === 'running' ? Math.sin(progress * Math.PI * 2) * 0.35 : 0;
  });

  return (
    <group ref={group} position={position}>
      <mesh castShadow position={[0, 0.26, 0]}>
        <boxGeometry args={[1.1, 0.38, 0.72]} />
        <meshStandardMaterial color="#24272d" roughness={0.58} />
      </mesh>
      <mesh castShadow position={[0, 0.48, 0]}>
        <boxGeometry args={[0.82, 0.18, 0.5]} />
        <meshStandardMaterial color="#14161a" roughness={0.4} />
      </mesh>
      <mesh castShadow position={[-0.46, 0.18, 0]}>
        <boxGeometry args={[0.14, 0.22, 0.76]} />
        <meshStandardMaterial color="#1f2023" />
      </mesh>
      <mesh castShadow position={[0.46, 0.18, 0]}>
        <boxGeometry args={[0.14, 0.22, 0.76]} />
        <meshStandardMaterial color="#1f2023" />
      </mesh>
      <mesh position={[0.3, 0.5, 0.18]}>
        <sphereGeometry args={[0.05, 16, 16]} />
        <meshStandardMaterial
          color={status === 'running' ? '#6bffb7' : '#8a8f98'}
          emissive={status === 'running' ? '#6bffb7' : '#111111'}
          emissiveIntensity={0.8}
        />
      </mesh>
    </group>
  );
}

export default function SunroomModel() {
  const layout = useTwinStore((state) => state.layout);
  const devices = useTwinStore((state) => state.devices);
  const selectedDeviceId = useTwinStore((state) => state.selectedDeviceId);
  const selectDevice = useTwinStore((state) => state.selectDevice);

  const [agentDataset, setAgentDataset] = useState([]);
  const [agentError, setAgentError] = useState(null);

  useEffect(() => {
    let alive = true;
    let timer = null;

    const fetchAgentDataset = async () => {
      try {
        const response = await fetch('/api/v1/agents/status', {
          method: 'GET',
          headers: {
            Accept: 'application/json'
          }
        });

        if (!response.ok) {
          throw new Error(`agent status request failed: ${response.status}`);
        }

        const data = await response.json();
        if (!alive) return;

        setAgentDataset(Array.isArray(data) ? data : []);
        setAgentError(null);
      } catch (error) {
        if (!alive) return;
        console.error('fetch agent dataset failed:', error);
        setAgentError(error);
      }
    };

    fetchAgentDataset();
    timer = window.setInterval(fetchAgentDataset, 1000);

    return () => {
      alive = false;
      if (timer) window.clearInterval(timer);
    };
  }, []);

  const deviceMap = useMemo(() => deviceMapFromList(devices), [devices]);

  const defaultBuilding = {
    dimensions: { length: 11.28, width: 5.2, platformHeight: 0.18 },
    platform: { stepDepth: 0.42, entryStepWidth: 2.85 },

    restZone: {
      center: [-2.22, 0, -1.34],
      size: [4.35, 0, 1.78],
      wallHeight: 1.8
    },

    monitors: [
      { id: 'monitor.top', center: [2.38, 1.72, -2.14], size: [3.55, 1.8, 0.1], rotation: [0, 0, 0] },
      { id: 'monitor.right', center: [4.76, 1.72, -0.05], size: [3, 1.8, 0.1], rotation: [0, Math.PI / 2, 0] }
    ],

    roof: {
      main: {
        profile: [[-2.75, 2.42], [0.0, 4.02], [2.7, 2.82]],
        thickness: 0.1,
        depth: 11.6,
        position: [0, 0, 0]
      },
      upper: {
        profile: [[-1.15, 3.82], [0.55, 4.38], [2.35, 4.0]],
        thickness: 0.08,
        depth: 9.7,
        position: [0.35, 0, -0.12]
      },
      entry: {
        profile: [[-3.0, 2.12], [-1.75, 2.75], [-0.45, 2.35]],
        thickness: 0.08,
        depth: 11.75,
        position: [0, 0, 0]
      }
    },

    braceXs: [-4.8, -2.9, -0.35, 1.9, 4.1],
    deviceAnchors: {}
  };

  const building = {
    ...defaultBuilding,
    ...(layout?.building || {}),
    meetingTable: defaultBuilding.meetingTable
  };
  const dims = building.dimensions || defaultBuilding.dimensions;
  const length = dims.length;
  const width = dims.width;
  const platformHeight = dims.platformHeight;
  const halfLength = length / 2;
  const halfWidth = width / 2;

  const perimeterLight = deviceMap['light.perimeter']?.state || { on: true, brightness: 58, cct: 4200 };
  const entryLight = deviceMap['light.entry']?.state || { on: false, brightness: 0 };
  const windowState = deviceMap['window.north']?.state || { position: 0 };
  const curtain = deviceMap['curtain.front']?.state || { position: 100 };
  const ac = deviceMap['ac.main']?.state || { power: true, mode: 'cool' };
  const freshair = deviceMap['freshair.main']?.state || { power: true, mode: 'normal' };
  const robot = deviceMap['robot.openclaw']?.state || { status: 'docked', progress: 0 };
  const mainScreen = deviceMap['screen.main']?.state || { on: true, mode: 'dashboard', message: '阳光房 Digital Twin 已连接' };

  const lightColor = cctToColor(perimeterLight.cct);
  const perimeterEmissive = perimeterLight.on ? clamp01((perimeterLight.brightness || 0) / 80) : 0.02;
  const entryEmissive = entryLight.on ? clamp01((entryLight.brightness || 0) / 80) : 0.02;
  const windowSlide = ((windowState.position || 0) / 100) * 0.62;
  const curtainDrop = 2.05 * (1 - (curtain.position || 0) / 100);

  const anchors = building.deviceAnchors || {};

  const workDesks = [
    [-3.95, 0, 0.68],
    [-2.65, 0, 0.68],
    [-1.35, 0, 0.68]
  ];
  const meetingTable = building.meetingTable || layout?.building?.meetingTable || { center: [2.3, 0.76, -0.05], size: [1.55, 0.08, 2.6] };
  const meetingTableCenter = [
    (meetingTable.center?.[0] ?? 2.3) + MEETING_ZONE_SHIFT_X,
    0,
    meetingTable.center?.[2] ?? -0.05
  ];
  const meetingTableSize = [
    meetingTable.size?.[0] ?? 1.55,
    0,
    meetingTable.size?.[2] ?? 2.6
  ];
  const meetingTopZ = meetingTableCenter[2] + meetingTableSize[2] / 2 + 0.62;
  const meetingBottomZ = meetingTableCenter[2] - meetingTableSize[2] / 2 - 0.62;
  const meetingLeftX = meetingTableCenter[0] - meetingTableSize[0] / 2 - 0.58;
  const meetingRightX = meetingTableCenter[0] + meetingTableSize[0] / 2 + 0.58;
  const meetingColumnSpread = meetingTableSize[0] * 0.32;

  const workChairs = [
    [-4.72, 0, 0.68],
    [-3.42, 0, 0.68],
    [-2.12, 0, 0.68]
  ];

  const meetingChairs = [
    [meetingTableCenter[0] - meetingColumnSpread, 0, meetingTopZ],
    [meetingTableCenter[0], 0, meetingTopZ],
    [meetingTableCenter[0] + meetingColumnSpread, 0, meetingTopZ],
    [meetingTableCenter[0] - meetingColumnSpread, 0, meetingBottomZ],
    [meetingTableCenter[0], 0, meetingBottomZ],
    [meetingTableCenter[0] + meetingColumnSpread, 0, meetingBottomZ],
    [meetingLeftX, 0, meetingTableCenter[2]],
    [meetingRightX, 0, meetingTableCenter[2]]
  ];

  const characterChairs = [
    ...workChairs.map((pos, index) => ({
      position: pos,
      zone: 'work',
      rot: Math.PI / 2,
      seatPosition: [pos[0] + 0.12, 0, pos[2]],
      focusPoint: [workDesks[index][0], GROUND_Y, workDesks[index][2]]
    })),
    ...meetingChairs.map((pos, index) => {
      const rotations = [
        Math.PI,
        Math.PI,
        Math.PI,
        0,
        0,
        0,
        Math.PI / 2,
        -Math.PI / 2
      ];

      return {
        position: pos,
        zone: 'meeting',
        rot: rotations[index],
        seatPosition: [pos[0], 0, pos[2]],
        focusPoint: [meetingTableCenter[0], GROUND_Y, meetingTableCenter[2]]
      };
    })
  ];

  const meetingActive = useMemo(() => agentDataset.some((item) => item.status === 'meet'), [agentDataset]);
  const workingCount = useMemo(() => agentDataset.filter((item) => item.status === 'work').length, [agentDataset]);
  const meetingCount = useMemo(() => agentDataset.filter((item) => item.status === 'meet').length, [agentDataset]);

  const navigationConfig = useMemo(() => {
    const restCenter = building.restZone.center || defaultBuilding.restZone.center;
    const restSize = building.restZone.size || defaultBuilding.restZone.size;
    const restWallHeight = building.restZone.wallHeight || defaultBuilding.restZone.wallHeight;
    const restWallObstacles = getRestZoneWallObstacles(restCenter, restSize, restWallHeight, 0.12, 0.9);
    const workDeskObstacles = getWorkDeskObstacles(workDesks);
    const meetingTableObstacle = getMeetingTableObstacle(meetingTableCenter, meetingTableSize);
    const robotAnchor = anchors['robot.openclaw'] || [-5.0, 0.33, 2.15];
    const robotObstacle = getRobotObstacle(robotAnchor, robot.status, robot.progress || 0);
    const obstacles = [...restWallObstacles, ...workDeskObstacles, meetingTableObstacle, robotObstacle];

    return buildNavigationConfig({
      bounds: {
        minX: -halfLength + 0.2,
        maxX: halfLength - 0.2,
        minZ: -halfWidth + 0.2,
        maxZ: halfWidth - 0.2
      },
      obstacles
    });
  }, [anchors, robot.status, robot.progress, building.restZone.center, building.restZone.size, building.restZone.wallHeight, defaultBuilding.restZone.center, defaultBuilding.restZone.size, defaultBuilding.restZone.wallHeight, meetingTableCenter, meetingTableSize, halfLength, halfWidth]);

  const characterCount = useMemo(() => {
    if (agentDataset.length > 0) return agentDataset.length;
    return 3;
  }, [agentDataset.length]);

  return (
    <group position={[0, 0, 0]}>
      <mesh receiveShadow rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.1, 0]}>
        <planeGeometry args={[40, 40]} />
        <meshStandardMaterial color="#9fad98" roughness={0.98} />
      </mesh>

      <mesh castShadow receiveShadow position={[0, platformHeight / 2, 0]}>
        <boxGeometry args={[length, platformHeight, width]} />
        <meshStandardMaterial color="#d9dde0" roughness={0.9} />
      </mesh>

      <CurvedShell {...building.roof.main} color="#f4f2ea" opacity={0.32} />
      <CurvedShell {...building.roof.upper} color="#f6f5ef" opacity={0.24} />
      <CurvedShell {...building.roof.entry} color="#ece8df" opacity={0.24} />

      {[...Array(9)].map((_, index) => {
        const x = -halfLength + index * (length / 8);
        return (
          <React.Fragment key={`front-col-${index}`}>
            <mesh castShadow position={[x, 1.32, halfWidth - 0.02]}>
              <boxGeometry args={[0.08, 2.64, 0.08]} />
              <meshStandardMaterial color="#f5f1e9" />
            </mesh>
            <mesh castShadow position={[x, 1.32, -halfWidth + 0.02]}>
              <boxGeometry args={[0.08, 2.64, 0.08]} />
              <meshStandardMaterial color="#f5f1e9" />
            </mesh>
          </React.Fragment>
        );
      })}

      {[...Array(5)].map((_, index) => {
        const z = -halfWidth + index * (width / 4);
        return (
          <React.Fragment key={`side-col-${index}`}>
            <mesh castShadow position={[-halfLength + 0.02, 1.35, z]}>
              <boxGeometry args={[0.08, 2.7, 0.08]} />
              <meshStandardMaterial color="#f5f1e9" />
            </mesh>
            <mesh castShadow position={[halfLength - 0.02, 1.35, z]}>
              <boxGeometry args={[0.08, 2.7, 0.08]} />
              <meshStandardMaterial color="#f5f1e9" />
            </mesh>
          </React.Fragment>
        );
      })}

      <mesh position={[0, 2.66, halfWidth - 0.02]} castShadow>
        <boxGeometry args={[length, 0.08, 0.08]} />
        <meshStandardMaterial color="#f5f1e9" />
      </mesh>
      <mesh position={[0, 2.66, -halfWidth + 0.02]} castShadow>
        <boxGeometry args={[length, 0.08, 0.08]} />
        <meshStandardMaterial color="#f5f1e9" />
      </mesh>

      {[...Array(8)].map((_, index) => {
        const bayWidth = length / 8 - 0.16;
        const x = -halfLength + bayWidth / 2 + 0.08 + index * (length / 8);
        return (
          <React.Fragment key={`glass-bays-${index}`}>
            <mesh position={[x, 1.32, halfWidth - 0.05]} receiveShadow>
              <boxGeometry args={[bayWidth, 2.56, 0.03]} />
              <meshStandardMaterial
                color="#bfe9ff"
                transparent
                opacity={0.18}
                metalness={0.05}
                roughness={0.1}
              />
            </mesh>
            <mesh position={[x, 1.32, -halfWidth + 0.05]} receiveShadow>
              <boxGeometry args={[bayWidth, 2.56, 0.03]} />
              <meshStandardMaterial
                color="#bfe9ff"
                transparent
                opacity={0.18}
                metalness={0.05}
                roughness={0.1}
              />
            </mesh>
          </React.Fragment>
        );
      })}

      {(building.braceXs || []).map((x) => (
        <React.Fragment key={`brace-${x}`}>
          <Beam start={[x, 0.18, halfWidth - 0.12]} end={[x + 0.55, 2.64, halfWidth - 0.12]} />
          <Beam start={[x + 0.95, 0.18, -halfWidth + 0.12]} end={[x + 0.35, 2.7, -halfWidth + 0.12]} />
        </React.Fragment>
      ))}

      <RestZonePartition
        center={building.restZone.center}
        size={building.restZone.size}
        height={building.restZone.wallHeight}
      />

      {workDesks.map((position, index) => (
        <React.Fragment key={`work-desk-${index}`}>
          <WorkDesk position={position} />
          <Laptop
            position={[position[0] + 0.02, 0.83, position[2]]}
            rotation={[0, -Math.PI / 2, 0]}
            accent={index === 1 ? '#8de2ff' : '#68b8ff'}
            active
          />
        </React.Fragment>
      ))}

      {workChairs.map((position, index) => (
        <Chair key={`work-chair-${index}`} position={position} rotation={[0, Math.PI / 2, 0]} />
      ))}

      <mesh castShadow receiveShadow position={[meetingTableCenter[0], meetingTable.center?.[1] ?? 0.76, meetingTableCenter[2]]}>
        <boxGeometry args={[meetingTableSize[0], meetingTable.size?.[1] ?? 0.08, meetingTableSize[2]]} />
        <meshStandardMaterial color="#cfa97d" roughness={0.65} />
      </mesh>

      <Laptop
        position={[meetingTableCenter[0] - meetingTableSize[0] * 0.18, 0.85, meetingTableCenter[2] - 0.08]}
        rotation={[0, Math.PI / 5, 0]}
        accent={meetingActive ? '#78d7ff' : '#586878'}
        active={meetingActive}
      />
      <Laptop
        position={[meetingTableCenter[0] + meetingTableSize[0] * 0.2, 0.85, meetingTableCenter[2] + 0.14]}
        rotation={[0, -Math.PI / 4, 0]}
        accent={meetingActive ? '#9fe9ff' : '#586878'}
        active={meetingActive}
      />

      <Beam
        start={[meetingTableCenter[0] - meetingTableSize[0] * 0.39, 0.04, meetingTableCenter[2] - meetingTableSize[2] * 0.34]}
        end={[meetingTableCenter[0] - meetingTableSize[0] * 0.39, meetingTable.center?.[1] ?? 0.76, meetingTableCenter[2] - meetingTableSize[2] * 0.34]}
        radius={0.04}
        color="#8e9499"
      />
      <Beam
        start={[meetingTableCenter[0] + meetingTableSize[0] * 0.39, 0.04, meetingTableCenter[2] - meetingTableSize[2] * 0.34]}
        end={[meetingTableCenter[0] + meetingTableSize[0] * 0.39, meetingTable.center?.[1] ?? 0.76, meetingTableCenter[2] - meetingTableSize[2] * 0.34]}
        radius={0.04}
        color="#8e9499"
      />
      <Beam
        start={[meetingTableCenter[0] - meetingTableSize[0] * 0.39, 0.04, meetingTableCenter[2] + meetingTableSize[2] * 0.34]}
        end={[meetingTableCenter[0] - meetingTableSize[0] * 0.39, meetingTable.center?.[1] ?? 0.76, meetingTableCenter[2] + meetingTableSize[2] * 0.34]}
        radius={0.04}
        color="#8e9499"
      />
      <Beam
        start={[meetingTableCenter[0] + meetingTableSize[0] * 0.39, 0.04, meetingTableCenter[2] + meetingTableSize[2] * 0.34]}
        end={[meetingTableCenter[0] + meetingTableSize[0] * 0.39, meetingTable.center?.[1] ?? 0.76, meetingTableCenter[2] + meetingTableSize[2] * 0.34]}
        radius={0.04}
        color="#8e9499"
      />

      {meetingChairs.map((position, index) => {
        const rotations = [
          [0, Math.PI, 0],
          [0, Math.PI, 0],
          [0, Math.PI, 0],
          [0, 0, 0],
          [0, 0, 0],
          [0, 0, 0],
          [0, Math.PI / 2, 0],
          [0, -Math.PI / 2, 0]
        ];
        return <Chair key={`meeting-chair-${index}`} position={position} rotation={rotations[index]} />;
      })}

      {building.monitors.map((item) => {
        const isMeetingScreen = item.id === 'monitor.right';
        const mode = !mainScreen.on && isMeetingScreen
          ? 'off'
          : meetingActive
            ? (isMeetingScreen ? 'meeting' : 'dashboard')
            : (isMeetingScreen ? mainScreen.mode || 'dashboard' : 'dashboard');
        const title = isMeetingScreen
          ? (meetingActive ? '协作讨论中' : 'Sunroom Control')
          : (meetingActive ? '工位状态总览' : '工位联动状态');
        const subtitle = isMeetingScreen
          ? (meetingActive ? `参会 Agent ${meetingCount} 名` : (mainScreen.message || '环境与设备状态稳定'))
          : (meetingActive ? `会议进行中，工位工作中 ${workingCount} 名` : `当前工作中 ${workingCount} 名 Agent`);

        return (
        <ScreenDisplay
          key={item.id}
          position={item.center}
          rotation={item.rotation}
          size={item.size}
          mode={mode}
          title={title}
          subtitle={subtitle}
          doubleSided={item.id === 'monitor.top'}
        />
        );
      })}

      <mesh position={[-4.1, 2.56 + windowSlide * 0.45, -halfWidth + 0.05]} castShadow>
        <boxGeometry args={[2.35, 0.5, 0.05]} />
        <meshStandardMaterial color="#d4f0ff" transparent opacity={0.22} roughness={0.1} />
      </mesh>

      <mesh position={[0, 2.65 - curtainDrop / 2, halfWidth - 0.14]}>
        <boxGeometry args={[length - 1.0, Math.max(0.08, curtainDrop), 0.04]} />
        <meshStandardMaterial color="#d8ccb6" transparent opacity={0.58} roughness={0.72} />
      </mesh>

      <mesh position={[-0.35, 2.42, -1.75]} castShadow>
        <boxGeometry args={[1.05, 0.34, 0.26]} />
        <meshStandardMaterial
          color={ac.power ? '#f3f7fb' : '#cdd4da'}
          emissive={ac.power ? '#78cfff' : '#000000'}
          emissiveIntensity={ac.power ? 0.16 : 0}
        />
      </mesh>

      <mesh position={[1.15, 2.25, -1.78]} castShadow>
        <boxGeometry args={[0.7, 0.52, 0.28]} />
        <meshStandardMaterial
          color={freshair.power ? '#f2f6f7' : '#cfd4d6'}
          emissive={freshair.power ? '#70d4c8' : '#000000'}
          emissiveIntensity={freshair.power ? 0.15 : 0}
        />
      </mesh>

      <mesh position={[0, 2.74, halfWidth - 0.18]}>
        <boxGeometry args={[length - 1.05, 0.05, 0.07]} />
        <meshStandardMaterial color={lightColor} emissive={lightColor} emissiveIntensity={perimeterEmissive} />
      </mesh>

      <mesh position={[0, 2.74, -halfWidth + 0.18]}>
        <boxGeometry args={[length - 1.05, 0.05, 0.07]} />
        <meshStandardMaterial
          color={lightColor}
          emissive={lightColor}
          emissiveIntensity={perimeterEmissive * 0.8}
        />
      </mesh>

      <mesh position={[0, 2.38, halfWidth + 0.18]}>
        <boxGeometry args={[length - 1.15, 0.05, 0.07]} />
        <meshStandardMaterial color="#ffd2a0" emissive="#ffd2a0" emissiveIntensity={entryEmissive} />
      </mesh>

      <Robot
        position={anchors['robot.openclaw'] || [-5.0, 0.33, 2.15]}
        status={robot.status}
        progress={robot.progress || 0}
      />

      <CharacterManager
        dataset={agentDataset}
        count={characterCount}
        chairs={characterChairs}
        navConfig={navigationConfig}
      />

      {devices.map((device) => {
        const anchor = anchors[device.id];
        if (!anchor) return null;
        return (
          <Marker
            key={device.id}
            position={anchor}
            label={device.name}
            color={domainColor(device.domain)}
            active={selectedDeviceId === device.id}
            onClick={() => selectDevice(device.id)}
          />
        );
      })}

      <Html transform position={[-2.25, 0.42, -1.0]} distanceFactor={12}>
        <div className="zone-label">休息区</div>
      </Html>

      <Html transform position={[-1.95, 0.42, 1.35]} distanceFactor={12}>
        <div className="zone-label">工作区</div>
      </Html>

      <Html transform position={[2.75, 0.42, 1.35]} distanceFactor={12}>
        <div className="zone-label">讨论区</div>
      </Html>

      {agentError ? (
        <Html transform position={[0, 3.3, 0]} distanceFactor={14}>
          <div
            style={{
              padding: '6px 10px',
              borderRadius: 8,
              background: 'rgba(180,40,40,0.85)',
              color: '#fff',
              fontSize: 12,
              whiteSpace: 'nowrap'
            }}
          >
            Agent 数据读取失败
          </div>
        </Html>
      ) : null}
    </group>
  );
}
