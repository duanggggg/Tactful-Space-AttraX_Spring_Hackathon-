import * as THREE from 'three';

const GRID_SIZE = 0.18;
const DEFAULT_CLEARANCE = 0.2;

function pointInRect(x, z, rect) {
  return x >= rect.minX && x <= rect.maxX && z >= rect.minZ && z <= rect.maxZ;
}

function segmentIntersectsRect(a, b, rect) {
  if (pointInRect(a.x, a.z, rect) || pointInRect(b.x, b.z, rect)) return true;

  const minX = Math.min(a.x, b.x);
  const maxX = Math.max(a.x, b.x);
  const minZ = Math.min(a.z, b.z);
  const maxZ = Math.max(a.z, b.z);
  if (maxX < rect.minX || minX > rect.maxX || maxZ < rect.minZ || minZ > rect.maxZ) {
    return false;
  }

  const dx = b.x - a.x;
  const dz = b.z - a.z;
  let t0 = 0;
  let t1 = 1;

  const clip = (p, q) => {
    if (p === 0) return q >= 0;
    const r = q / p;
    if (p < 0) {
      if (r > t1) return false;
      if (r > t0) t0 = r;
    } else {
      if (r < t0) return false;
      if (r < t1) t1 = r;
    }
    return true;
  };

  if (
    clip(-dx, a.x - rect.minX) &&
    clip(dx, rect.maxX - a.x) &&
    clip(-dz, a.z - rect.minZ) &&
    clip(dz, rect.maxZ - a.z)
  ) {
    return t1 >= t0;
  }
  return false;
}

function isWalkable(x, z, obstacles, bounds) {
  if (x < bounds.minX || x > bounds.maxX || z < bounds.minZ || z > bounds.maxZ) {
    return false;
  }
  return !obstacles.some((rect) => pointInRect(x, z, rect));
}

function findNearestWalkablePoint(point, navConfig, y) {
  const { bounds, obstacles, origin } = navConfig;
  if (isWalkable(point.x, point.z, obstacles, bounds)) {
    return point.clone();
  }

  const startIx = toGrid(point.x, origin.x);
  const startIz = toGrid(point.z, origin.z);
  const maxRadius = 24;

  for (let radius = 1; radius <= maxRadius; radius += 1) {
    for (let dx = -radius; dx <= radius; dx += 1) {
      for (let dz = -radius; dz <= radius; dz += 1) {
        if (Math.max(Math.abs(dx), Math.abs(dz)) !== radius) continue;
        const candidateX = toWorld(startIx + dx, origin.x);
        const candidateZ = toWorld(startIz + dz, origin.z);
        if (!isWalkable(candidateX, candidateZ, obstacles, bounds)) continue;
        return new THREE.Vector3(candidateX, y, candidateZ);
      }
    }
  }

  return point.clone();
}

function gridKey(ix, iz) {
  return `${ix},${iz}`;
}

function toGrid(value, origin) {
  return Math.round((value - origin) / GRID_SIZE);
}

function toWorld(index, origin) {
  return origin + index * GRID_SIZE;
}

function heuristic(a, b) {
  const dx = a.ix - b.ix;
  const dz = a.iz - b.iz;
  return Math.sqrt(dx * dx + dz * dz);
}

function reconstructPath(cameFrom, currentKey, origin, y) {
  const path = [];
  let key = currentKey;
  while (key) {
    const [ix, iz] = key.split(',').map(Number);
    path.push(new THREE.Vector3(toWorld(ix, origin.x), y, toWorld(iz, origin.z)));
    key = cameFrom.get(key) || null;
  }
  return path.reverse();
}

function hasLineOfSight(a, b, obstacles) {
  return !obstacles.some((rect) => segmentIntersectsRect(a, b, rect));
}

function smoothPath(path, obstacles) {
  if (path.length <= 2) return path;
  const smoothed = [path[0]];
  let anchorIndex = 0;

  while (anchorIndex < path.length - 1) {
    let furthest = anchorIndex + 1;
    for (let index = anchorIndex + 2; index < path.length; index += 1) {
      if (!hasLineOfSight(path[anchorIndex], path[index], obstacles)) break;
      furthest = index;
    }
    smoothed.push(path[furthest]);
    anchorIndex = furthest;
  }

  return smoothed;
}

export function buildNavigationConfig({ bounds, obstacles }) {
  const inflatedObstacles = obstacles.map((rect) => ({
    minX: rect.minX - DEFAULT_CLEARANCE,
    maxX: rect.maxX + DEFAULT_CLEARANCE,
    minZ: rect.minZ - DEFAULT_CLEARANCE,
    maxZ: rect.maxZ + DEFAULT_CLEARANCE
  }));

  return {
    bounds,
    obstacles: inflatedObstacles,
    origin: {
      x: bounds.minX,
      z: bounds.minZ
    }
  };
}

export function findPath(start, goal, navConfig, y = 0.12) {
  if (!navConfig) return [start.clone(), goal.clone()];
  const { obstacles, origin } = navConfig;
  const safeStart = findNearestWalkablePoint(start, navConfig, y);
  const safeGoal = findNearestWalkablePoint(goal, navConfig, y);

  if (hasLineOfSight(safeStart, safeGoal, obstacles)) {
    return [start.clone(), safeStart, safeGoal].filter((point, index, arr) => {
      if (index === 0) return true;
      return point.distanceTo(arr[index - 1]) > 0.001;
    });
  }

  const startNode = { ix: toGrid(safeStart.x, origin.x), iz: toGrid(safeStart.z, origin.z) };
  const goalNode = { ix: toGrid(safeGoal.x, origin.x), iz: toGrid(safeGoal.z, origin.z) };

  const startKey = gridKey(startNode.ix, startNode.iz);
  const goalKey = gridKey(goalNode.ix, goalNode.iz);
  const open = new Map([[startKey, { ...startNode, f: heuristic(startNode, goalNode), g: 0 }]]);
  const cameFrom = new Map();
  const gScore = new Map([[startKey, 0]]);
  const closed = new Set();

  const directions = [
    [-1, 0], [1, 0], [0, -1], [0, 1],
    [-1, -1], [-1, 1], [1, -1], [1, 1]
  ];

  while (open.size > 0) {
    let currentEntry = null;
    for (const entry of open.values()) {
      if (!currentEntry || entry.f < currentEntry.f) currentEntry = entry;
    }
    if (!currentEntry) break;

    const currentKey = gridKey(currentEntry.ix, currentEntry.iz);
    if (currentKey === goalKey) {
      const rawPath = reconstructPath(cameFrom, currentKey, origin, y);
      rawPath[0] = safeStart.clone();
      rawPath[rawPath.length - 1] = safeGoal.clone();
      const smoothed = smoothPath(rawPath, obstacles);
      return [start.clone(), ...smoothed].filter((point, index, arr) => {
        if (index === 0) return true;
        return point.distanceTo(arr[index - 1]) > 0.001;
      });
    }

    open.delete(currentKey);
    closed.add(currentKey);

    for (const [dx, dz] of directions) {
      const nextIx = currentEntry.ix + dx;
      const nextIz = currentEntry.iz + dz;
      const nextKey = gridKey(nextIx, nextIz);
      if (closed.has(nextKey)) continue;

      const nextX = toWorld(nextIx, origin.x);
      const nextZ = toWorld(nextIz, origin.z);
      if (!isWalkable(nextX, nextZ, obstacles, navConfig.bounds)) continue;

      if (dx !== 0 && dz !== 0) {
        const sideAX = toWorld(currentEntry.ix + dx, origin.x);
        const sideAZ = toWorld(currentEntry.iz, origin.z);
        const sideBX = toWorld(currentEntry.ix, origin.x);
        const sideBZ = toWorld(currentEntry.iz + dz, origin.z);
        if (
          !isWalkable(sideAX, sideAZ, obstacles, navConfig.bounds) ||
          !isWalkable(sideBX, sideBZ, obstacles, navConfig.bounds)
        ) {
          continue;
        }
      }

      const stepCost = dx !== 0 && dz !== 0 ? Math.SQRT2 : 1;
      const tentativeG = (gScore.get(currentKey) || 0) + stepCost;
      if (tentativeG >= (gScore.get(nextKey) ?? Number.POSITIVE_INFINITY)) continue;

      cameFrom.set(nextKey, currentKey);
      gScore.set(nextKey, tentativeG);
      open.set(nextKey, {
        ix: nextIx,
        iz: nextIz,
        g: tentativeG,
        f: tentativeG + heuristic({ ix: nextIx, iz: nextIz }, goalNode)
      });
    }
  }

  return [start.clone(), safeStart, safeGoal].filter((point, index, arr) => {
    if (index === 0) return true;
    return point.distanceTo(arr[index - 1]) > 0.001;
  });
}
