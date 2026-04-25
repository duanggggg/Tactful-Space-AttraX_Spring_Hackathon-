import React, { useMemo, useRef, useEffect, useState } from 'react';
import { Html } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { findPath } from './pathfinding.js';

/* ------------------ 常量 ------------------ */

const AGENT_RADIUS = 0.18;
const GROUND_Y = 0.12;
const MOVE_SPEED = 1.25;

const REST_POINTS = [
  new THREE.Vector3(-3.15, GROUND_Y, -1.62),
  new THREE.Vector3(-2.75, GROUND_Y, -1.22),
  new THREE.Vector3(-2.25, GROUND_Y, -1.5),
  new THREE.Vector3(-1.8, GROUND_Y, -1.12),
  new THREE.Vector3(-1.42, GROUND_Y, -1.56)
];

const STATES = {
  IDLE: 'idle',
  ACTING: 'acting'
};

const ACTIONS = {
  WORK: 'work',
  REST: 'rest',
  MEET: 'meet',
  IDLE: 'idle'
};

const ACTION_LABEL = {
  work: '工作中',
  rest: '休息中',
  meet: '开会中',
  idle: '空闲'
};

const NAME_POOL = ['空调', '灯光', '电脑'];
const COLOR_POOL = ['#ff6b6b', '#4ecdc4', '#45b7d1', '#ffeaa7', '#a78bfa', '#f472b6'];

/* ------------------ 工具 ------------------ */

function shuffle(arr) {
  return [...arr].sort(() => Math.random() - 0.5);
}

function isTooCloseToOthers(pos, current, agentsRef, minDistance = AGENT_RADIUS * 2.2) {
  return false;
}

function releaseRestPointIfNeeded(agentState, restPointOccupancyRef) {
  if (agentState.restPointIndex !== null) {
    restPointOccupancyRef.current[agentState.restPointIndex] = false;
    agentState.restPointIndex = null;
  }
}

function releaseChairIfNeeded(agentState, chairOccupancyRef) {
  if (agentState.chairIndex !== null) {
    chairOccupancyRef.current[agentState.chairIndex] = false;
    agentState.chairIndex = null;
  }
}

function getSpawnFromRestPool(existingAgents, restPointOccupancyRef) {
  const order = shuffle(REST_POINTS.map((_, index) => index));

  for (const idx of order) {
    if (restPointOccupancyRef.current[idx]) continue;

    const pos = REST_POINTS[idx].clone();

    let tooClose = false;
    for (const other of existingAgents) {
      if (pos.distanceTo(other) < AGENT_RADIUS * 2.2) {
        tooClose = true;
        break;
      }
    }

    if (tooClose) continue;

    restPointOccupancyRef.current[idx] = true;
    return { pos, restPointIndex: idx };
  }

  const idx = 0;
  restPointOccupancyRef.current[idx] = true;
  return { pos: REST_POINTS[idx].clone(), restPointIndex: idx };
}

function findRestPointForStatus(restPointOccupancyRef, agentsRef, currentPos) {
  const freeIndices = REST_POINTS
    .map((_, index) => index)
    .filter((index) => !restPointOccupancyRef.current[index]);

  for (const index of freeIndices) {
    const pos = REST_POINTS[index].clone();
    if (!isTooCloseToOthers(pos, currentPos, agentsRef)) {
      return { index, pos };
    }
  }

  return null;
}

function findChairForStatus(chairs, chairOccupancyRef, zone, agentsRef, currentPos) {
  const candidates = chairs
    .map((chair, index) => ({ chair, index }))
    .filter(({ chair, index }) => chair.zone === zone && !chairOccupancyRef.current[index]);

  for (const item of shuffle(candidates)) {
    const pos = (item.chair.seatPosition || item.chair.interactPos).clone();
    if (!isTooCloseToOthers(pos, currentPos, agentsRef)) {
      return {
        index: item.index,
        pos,
        focusPoint: item.chair.focusPoint?.clone() || null
      };
    }
  }

  return null;
}

function PathTrace({ points, color }) {
  const positions = useMemo(() => {
    if (!points || points.length < 2) return null;
    return new Float32Array(points.flatMap((point) => [point.x, point.y + 0.03, point.z]));
  }, [points]);

  if (!positions) return null;

  return (
    <line>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color={color} transparent opacity={0.85} />
    </line>
  );
}

/* ------------------ Character ------------------ */

export const Character = React.memo(function Character({
  position,
  color,
  name,
  chairs,
  agentData,
  navConfig,
  agentsRef,
  chairOccupancyRef,
  restPointOccupancyRef,
  initialRestPointIndex = null
}) {
  const ref = useRef();
  const bodyRef = useRef();
  const torsoRef = useRef();
  const headRef = useRef();
  const leftUpperArmRef = useRef();
  const rightUpperArmRef = useRef();
  const leftForearmRef = useRef();
  const rightForearmRef = useRef();
  const leftThighRef = useRef();
  const rightThighRef = useRef();
  const leftShinRef = useRef();
  const rightShinRef = useRef();
  const actionTextRef = useRef(null);
  const [plannedPath, setPlannedPath] = useState([]);

  const runtime = useRef({
    current: new THREE.Vector3(...position),
    state: STATES.ACTING,
    actionType: ACTIONS.REST,
    restPointIndex: initialRestPointIndex,
    chairIndex: null,
    lastStatus: '__init__',
    route: [],
    routeIndex: 0,
    target: new THREE.Vector3(...position),
    facing: 0,
    focusTarget: null
  });

  useEffect(() => {
    agentsRef.current.push(runtime.current.current);

    if (actionTextRef.current) {
      actionTextRef.current.textContent = ACTION_LABEL[ACTIONS.REST];
    }

    return () => {
      agentsRef.current = agentsRef.current.filter((a) => a !== runtime.current.current);
      releaseRestPointIfNeeded(runtime.current, restPointOccupancyRef);
      releaseChairIfNeeded(runtime.current, chairOccupancyRef);
    };
  }, [agentsRef, chairOccupancyRef, restPointOccupancyRef]);

  const setIdle = () => {
    const s = runtime.current;
    releaseRestPointIfNeeded(s, restPointOccupancyRef);
    releaseChairIfNeeded(s, chairOccupancyRef);
    s.state = STATES.IDLE;
    s.actionType = ACTIONS.IDLE;
    s.route = [];
    s.routeIndex = 0;
    s.target.copy(s.current);
    s.focusTarget = null;
    setPlannedPath([]);
  };

  const planMove = (target, actionType, focusTarget = null) => {
    const s = runtime.current;
    const route = findPath(s.current.clone(), target.clone(), navConfig, GROUND_Y);
    s.route = route.slice(1);
    s.routeIndex = 0;
    s.target.copy(target);
    s.state = STATES.ACTING;
    s.actionType = actionType;
    s.focusTarget = focusTarget?.clone() || null;
    setPlannedPath(route);
  };

  const moveToRest = () => {
    const s = runtime.current;

    releaseChairIfNeeded(s, chairOccupancyRef);

    if (s.restPointIndex !== null) {
      s.state = STATES.ACTING;
      s.actionType = ACTIONS.REST;
      s.route = [];
      s.routeIndex = 0;
      s.target.copy(s.current);
      s.focusTarget = null;
      setPlannedPath([]);
      return;
    }

    const found = findRestPointForStatus(restPointOccupancyRef, agentsRef, s.current);
    if (!found) {
      setIdle();
      return;
    }

    restPointOccupancyRef.current[found.index] = true;
    s.restPointIndex = found.index;
    planMove(found.pos, ACTIONS.REST);
  };

  const moveToChairZone = (zone, actionType) => {
    const s = runtime.current;

    releaseRestPointIfNeeded(s, restPointOccupancyRef);

    if (s.chairIndex !== null) {
      const currentChair = chairs[s.chairIndex];
      if (currentChair && currentChair.zone === zone) {
        s.state = STATES.ACTING;
        s.actionType = actionType;
        s.focusTarget = currentChair.focusPoint?.clone() || null;
        return;
      }
      releaseChairIfNeeded(s, chairOccupancyRef);
    }

    const found = findChairForStatus(chairs, chairOccupancyRef, zone, agentsRef, s.current);
    if (!found) {
      setIdle();
      return;
    }

    chairOccupancyRef.current[found.index] = true;
    s.chairIndex = found.index;
    planMove(found.pos, actionType, found.focusPoint);
  };

  useEffect(() => {
    const s = runtime.current;
    const nextStatus = agentData?.status || ACTIONS.IDLE;

    if (nextStatus === s.lastStatus) return;
    s.lastStatus = nextStatus;

    if (nextStatus === ACTIONS.REST) {
      moveToRest();
      return;
    }

    if (nextStatus === ACTIONS.WORK) {
      moveToChairZone('work', ACTIONS.WORK);
      return;
    }

    if (nextStatus === ACTIONS.MEET) {
      moveToChairZone('meeting', ACTIONS.MEET);
      return;
    }

    setIdle();
  }, [agentData?.status, navConfig]);

  useFrame((_, delta) => {
    const obj = ref.current;
    if (!obj) return;

    const s = runtime.current;
    const nextWaypoint = s.route[s.routeIndex];
    let isMoving = false;
    let desiredFacing = s.facing;
    if (nextWaypoint) {
      const remaining = nextWaypoint.clone().sub(s.current);
      const distance = remaining.length();
      if (distance <= MOVE_SPEED * delta) {
        s.current.copy(nextWaypoint);
        s.routeIndex += 1;
      } else if (distance > 0) {
        isMoving = true;
        desiredFacing = Math.atan2(remaining.x, remaining.z);
        remaining.normalize().multiplyScalar(MOVE_SPEED * delta);
        s.current.add(remaining);
      }
    } else if (s.focusTarget && (s.actionType === ACTIONS.WORK || s.actionType === ACTIONS.MEET)) {
      const focusVector = s.focusTarget.clone().sub(s.current);
      if (focusVector.lengthSq() > 0.0001) {
        desiredFacing = Math.atan2(focusVector.x, focusVector.z);
      }
    }
    s.facing = desiredFacing;
    obj.position.set(s.current.x, GROUND_Y, s.current.z);
    obj.rotation.y = THREE.MathUtils.lerp(obj.rotation.y, s.facing, 0.18);

    const elapsed = performance.now() * 0.0015;
    const walkPhase = elapsed * 6.5;
    const idlePhase = elapsed * 2.0;
    const actionType = s.actionType;
    const isSeated = !isMoving && s.chairIndex !== null && (actionType === ACTIONS.WORK || actionType === ACTIONS.MEET);

    if (bodyRef.current) {
      bodyRef.current.position.y = isMoving ? Math.abs(Math.sin(walkPhase)) * 0.04 : (isSeated ? -0.3 : 0);
      bodyRef.current.position.z = isSeated ? -0.02 : 0;
    }
    if (torsoRef.current) {
      torsoRef.current.rotation.x = actionType === ACTIONS.WORK
        ? (isSeated ? -0.28 : -0.18) + Math.sin(elapsed * 8) * 0.03
        : actionType === ACTIONS.MEET
          ? (isSeated ? -0.12 : 0) + Math.sin(elapsed * 4) * 0.04
          : isMoving
            ? Math.sin(walkPhase * 2) * 0.05
            : Math.sin(idlePhase) * 0.02;
    }
    if (headRef.current) {
      headRef.current.rotation.y = actionType === ACTIONS.MEET ? Math.sin(elapsed * 3) * 0.18 : 0;
      headRef.current.rotation.x = actionType === ACTIONS.WORK ? 0.08 : Math.sin(idlePhase) * 0.03;
    }

    const walkArm = Math.sin(walkPhase) * 0.65;
    const walkLeg = Math.sin(walkPhase) * 0.75;
    const workPulse = Math.sin(elapsed * 10) * 0.12;
    const meetWave = Math.sin(elapsed * 5) * 0.45;

    if (leftUpperArmRef.current && rightUpperArmRef.current && leftForearmRef.current && rightForearmRef.current) {
      if (isMoving) {
        leftUpperArmRef.current.rotation.x = walkArm;
        rightUpperArmRef.current.rotation.x = -walkArm;
        leftForearmRef.current.rotation.x = Math.max(-0.2, -walkArm * 0.35);
        rightForearmRef.current.rotation.x = Math.max(-0.2, walkArm * 0.35);
      } else if (actionType === ACTIONS.WORK) {
        leftUpperArmRef.current.rotation.x = -1.05 + workPulse;
        rightUpperArmRef.current.rotation.x = -1.05 - workPulse;
        leftUpperArmRef.current.rotation.z = 0.22;
        rightUpperArmRef.current.rotation.z = -0.22;
        leftForearmRef.current.rotation.x = -0.9 + workPulse * 0.8;
        rightForearmRef.current.rotation.x = -0.9 - workPulse * 0.8;
      } else if (actionType === ACTIONS.MEET) {
        leftUpperArmRef.current.rotation.x = -0.45;
        rightUpperArmRef.current.rotation.x = -0.65 + meetWave * 0.5;
        leftUpperArmRef.current.rotation.z = 0.08;
        rightUpperArmRef.current.rotation.z = -0.35;
        leftForearmRef.current.rotation.x = -0.55;
        rightForearmRef.current.rotation.x = -0.9 + meetWave * 0.35;
      } else {
        leftUpperArmRef.current.rotation.x = 0.15 + Math.sin(idlePhase) * 0.03;
        rightUpperArmRef.current.rotation.x = -0.15 - Math.sin(idlePhase) * 0.03;
        leftUpperArmRef.current.rotation.z = 0.05;
        rightUpperArmRef.current.rotation.z = -0.05;
        leftForearmRef.current.rotation.x = -0.15;
        rightForearmRef.current.rotation.x = -0.15;
      }
    }

    if (leftThighRef.current && rightThighRef.current && leftShinRef.current && rightShinRef.current) {
      if (isMoving) {
        leftThighRef.current.rotation.x = -walkLeg;
        rightThighRef.current.rotation.x = walkLeg;
        leftShinRef.current.rotation.x = Math.max(0, -Math.sin(walkPhase + Math.PI / 2)) * 0.9;
        rightShinRef.current.rotation.x = Math.max(0, -Math.sin(walkPhase - Math.PI / 2)) * 0.9;
      } else if (actionType === ACTIONS.WORK) {
        leftThighRef.current.rotation.x = isSeated ? 1.2 : 0.9;
        rightThighRef.current.rotation.x = isSeated ? 1.2 : 0.9;
        leftShinRef.current.rotation.x = isSeated ? -1.6 : -1.35;
        rightShinRef.current.rotation.x = isSeated ? -1.6 : -1.35;
      } else if (actionType === ACTIONS.MEET) {
        leftThighRef.current.rotation.x = isSeated ? 1.05 : 0.62;
        rightThighRef.current.rotation.x = isSeated ? 1.05 : 0.62;
        leftShinRef.current.rotation.x = isSeated ? -1.45 : -1.1;
        rightShinRef.current.rotation.x = isSeated ? -1.45 : -1.1;
      } else {
        leftThighRef.current.rotation.x = 0;
        rightThighRef.current.rotation.x = 0;
        leftShinRef.current.rotation.x = 0;
        rightShinRef.current.rotation.x = 0;
      }
    }

    if (actionTextRef.current) {
      actionTextRef.current.textContent = ACTION_LABEL[s.actionType] || ACTION_LABEL.idle;
    }
  });

  return (
    <group ref={ref} position={[position[0], position[1], position[2]]}>
      <PathTrace points={plannedPath} color={color} />
      <group ref={bodyRef}>
        <group ref={torsoRef} position={[0, 0.82, 0]}>
          <mesh castShadow>
            <capsuleGeometry args={[0.17, 0.52, 6, 12]} />
            <meshStandardMaterial color={color} roughness={0.48} metalness={0.06} />
          </mesh>

          <mesh castShadow position={[0, 0.2, 0.13]}>
            <boxGeometry args={[0.22, 0.18, 0.16]} />
            <meshStandardMaterial color="#f4f6fb" roughness={0.82} />
          </mesh>

          <group ref={headRef} position={[0, 0.55, 0]}>
            <mesh castShadow>
              <sphereGeometry args={[0.17, 20, 20]} />
              <meshStandardMaterial color="#ffdbbf" />
            </mesh>
            <mesh castShadow position={[0, 0.1, -0.02]}>
              <sphereGeometry args={[0.175, 20, 20]} />
              <meshStandardMaterial color="#2b2b33" roughness={0.85} />
            </mesh>
            <mesh position={[0, 0.02, 0.16]}>
              <sphereGeometry args={[0.018, 10, 10]} />
              <meshStandardMaterial color="#1c1d22" />
            </mesh>
            <mesh position={[0.06, 0.03, 0.148]}>
              <sphereGeometry args={[0.02, 10, 10]} />
              <meshStandardMaterial color="#ffffff" roughness={0.2} />
            </mesh>
            <mesh position={[-0.06, 0.03, 0.148]}>
              <sphereGeometry args={[0.02, 10, 10]} />
              <meshStandardMaterial color="#ffffff" roughness={0.2} />
            </mesh>
            <mesh position={[0.063, 0.03, 0.162]}>
              <sphereGeometry args={[0.009, 8, 8]} />
              <meshStandardMaterial color="#1b1d23" />
            </mesh>
            <mesh position={[-0.057, 0.03, 0.162]}>
              <sphereGeometry args={[0.009, 8, 8]} />
              <meshStandardMaterial color="#1b1d23" />
            </mesh>
            <mesh position={[0.06, 0.085, 0.138]} rotation={[0, 0, 0.1]}>
              <boxGeometry args={[0.055, 0.008, 0.012]} />
              <meshStandardMaterial color="#2a211d" roughness={0.85} />
            </mesh>
            <mesh position={[-0.06, 0.085, 0.138]} rotation={[0, 0, -0.1]}>
              <boxGeometry args={[0.055, 0.008, 0.012]} />
              <meshStandardMaterial color="#2a211d" roughness={0.85} />
            </mesh>
            <mesh position={[0, -0.005, 0.166]} rotation={[0.25, 0, 0]}>
              <coneGeometry args={[0.012, 0.04, 10]} />
              <meshStandardMaterial color="#f1c2a0" roughness={0.9} />
            </mesh>
            <mesh position={[0, -0.065, 0.152]} rotation={[0, 0, 0]}>
              <torusGeometry args={[0.028, 0.0045, 8, 18, Math.PI]} />
              <meshStandardMaterial color="#b55b66" roughness={0.4} />
            </mesh>
          </group>

          <group ref={leftUpperArmRef} position={[0.24, 0.3, 0]}>
            <mesh castShadow position={[0, -0.16, 0]}>
              <capsuleGeometry args={[0.055, 0.26, 5, 10]} />
              <meshStandardMaterial color={color} roughness={0.5} />
            </mesh>
            <group ref={leftForearmRef} position={[0, -0.32, 0]}>
              <mesh castShadow position={[0, -0.14, 0]}>
                <capsuleGeometry args={[0.048, 0.24, 5, 10]} />
                <meshStandardMaterial color="#ffdbbf" roughness={0.6} />
              </mesh>
            </group>
          </group>

          <group ref={rightUpperArmRef} position={[-0.24, 0.3, 0]}>
            <mesh castShadow position={[0, -0.16, 0]}>
              <capsuleGeometry args={[0.055, 0.26, 5, 10]} />
              <meshStandardMaterial color={color} roughness={0.5} />
            </mesh>
            <group ref={rightForearmRef} position={[0, -0.32, 0]}>
              <mesh castShadow position={[0, -0.14, 0]}>
                <capsuleGeometry args={[0.048, 0.24, 5, 10]} />
                <meshStandardMaterial color="#ffdbbf" roughness={0.6} />
              </mesh>
            </group>
          </group>

          <group ref={leftThighRef} position={[0.1, -0.34, 0]}>
            <mesh castShadow position={[0, -0.19, 0]}>
              <capsuleGeometry args={[0.07, 0.34, 6, 12]} />
              <meshStandardMaterial color="#2f3540" roughness={0.65} />
            </mesh>
            <group ref={leftShinRef} position={[0, -0.39, 0]}>
              <mesh castShadow position={[0, -0.18, 0]}>
                <capsuleGeometry args={[0.058, 0.3, 6, 12]} />
                <meshStandardMaterial color="#49515e" roughness={0.64} />
              </mesh>
              <mesh castShadow position={[0, -0.38, 0.08]}>
                <boxGeometry args={[0.12, 0.06, 0.22]} />
                <meshStandardMaterial color="#1d2027" roughness={0.8} />
              </mesh>
            </group>
          </group>

          <group ref={rightThighRef} position={[-0.1, -0.34, 0]}>
            <mesh castShadow position={[0, -0.19, 0]}>
              <capsuleGeometry args={[0.07, 0.34, 6, 12]} />
              <meshStandardMaterial color="#2f3540" roughness={0.65} />
            </mesh>
            <group ref={rightShinRef} position={[0, -0.39, 0]}>
              <mesh castShadow position={[0, -0.18, 0]}>
                <capsuleGeometry args={[0.058, 0.3, 6, 12]} />
                <meshStandardMaterial color="#49515e" roughness={0.64} />
              </mesh>
              <mesh castShadow position={[0, -0.38, 0.08]}>
                <boxGeometry args={[0.12, 0.06, 0.22]} />
                <meshStandardMaterial color="#1d2027" roughness={0.8} />
              </mesh>
            </group>
          </group>
        </group>
      </group>

      <Html transform position={[0, 2.05, 0]} distanceFactor={10} sprite>
        <div
          style={{
            minWidth: 72,
            padding: '4px 6px',
            borderRadius: 8,
            background: 'rgba(20,20,24,0.82)',
            color: '#fff',
            fontSize: 12,
            lineHeight: 1.2,
            textAlign: 'center',
            userSelect: 'none',
            whiteSpace: 'nowrap',
            border: '1px solid rgba(255,255,255,0.12)'
          }}
        >
          <div style={{ fontWeight: 700 }}>{name}</div>
          <div ref={actionTextRef} style={{ opacity: 0.8, marginTop: 2 }}>
            空闲
          </div>
        </div>
      </Html>
    </group>
  );
});

/* ------------------ Manager ------------------ */

export const CharacterManager = React.memo(function CharacterManager({
  dataset = [],
  count = 5,
  chairs = [],
  navConfig = null
}) {
  const allChairs = useMemo(() => {
    return chairs.map((item) => {
      const [x, , z] = item.position || item;
      const zone = item.zone || 'meeting';
      const rot = item.rot || 0;
      const rawFocusPoint = item.focusPoint || null;
      const rawSeatPosition = item.seatPosition || null;

      let interactPos = new THREE.Vector3(x, GROUND_Y, z);

      if (zone === 'work') {
        interactPos = new THREE.Vector3(x + 0.18, GROUND_Y, z);
      } else if (zone === 'meeting') {
        if (Math.abs(rot - Math.PI) < 0.01) {
          interactPos = new THREE.Vector3(x, GROUND_Y, z + 0.34);
        } else if (Math.abs(rot) < 0.01) {
          interactPos = new THREE.Vector3(x, GROUND_Y, z - 0.34);
        } else if (Math.abs(rot - Math.PI / 2) < 0.01) {
          interactPos = new THREE.Vector3(x - 0.34, GROUND_Y, z);
        } else if (Math.abs(rot + Math.PI / 2) < 0.01) {
          interactPos = new THREE.Vector3(x + 0.34, GROUND_Y, z);
        }
      }

      return {
        pos: new THREE.Vector3(x, GROUND_Y, z),
        interactPos,
        seatPosition: rawSeatPosition ? new THREE.Vector3(rawSeatPosition[0], GROUND_Y, rawSeatPosition[2]) : interactPos.clone(),
        focusPoint: rawFocusPoint ? new THREE.Vector3(...rawFocusPoint) : null,
        zone,
        rot
      };
    });
  }, [chairs]);

  const datasetMap = useMemo(() => {
    const map = new Map();
    for (const item of dataset) {
      map.set(item.id, item);
    }
    return map;
  }, [dataset]);

  const agentsRef = useRef([]);
  const chairOccupancyRef = useRef(allChairs.map(() => false));
  const restPointOccupancyRef = useRef(REST_POINTS.map(() => false));

  const actualCount = Math.min(count, REST_POINTS.length, dataset.length || count);

  const chars = useMemo(() => {
    const initialAgents = [];
    const tempOccupancy = { current: REST_POINTS.map(() => false) };
    const created = [];

    for (let i = 0; i < actualCount; i += 1) {
      const { pos, restPointIndex } = getSpawnFromRestPool(initialAgents, tempOccupancy);
      initialAgents.push(pos);

      created.push({
        id: i + 1,
        name: NAME_POOL[i % NAME_POOL.length],
        position: [pos.x, pos.y, pos.z],
        color: COLOR_POOL[i % COLOR_POOL.length],
        initialRestPointIndex: restPointIndex
      });
    }

    return created;
  }, [actualCount]);

  useEffect(() => {
    chairOccupancyRef.current = allChairs.map(() => false);
  }, [allChairs]);

  useEffect(() => {
    const occupied = REST_POINTS.map(() => false);
    for (const c of chars) {
      if (c.initialRestPointIndex !== null && c.initialRestPointIndex !== undefined) {
        occupied[c.initialRestPointIndex] = true;
      }
    }
    restPointOccupancyRef.current = occupied;
  }, [chars]);

  return (
    <group>
      {chars.map((c) => (
        <Character
          key={c.id}
          position={c.position}
          color={c.color}
          name={c.name}
          chairs={allChairs}
          agentData={datasetMap.get(c.id)}
          navConfig={navConfig}
          agentsRef={agentsRef}
          chairOccupancyRef={chairOccupancyRef}
          restPointOccupancyRef={restPointOccupancyRef}
          initialRestPointIndex={c.initialRestPointIndex}
        />
      ))}
    </group>
  );
});

export default CharacterManager;
