import React from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Sky, ContactShadows } from '@react-three/drei';
import SunroomModel from './SunroomModel.jsx';

export default function SunroomCanvas() {
  return (
    <div className="canvas-shell">
      <Canvas
        camera={{ position: [13, 7.5, 14], fov: 42 }}
        shadows
        style={{ width: '100vw', height: '100vh', display: 'block' }}
      >
        <color attach="background" args={['#d8e4ea']} />
        <ambientLight intensity={0.75} />
        <directionalLight
          position={[12, 18, 9]}
          intensity={1.4}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
        />
        <hemisphereLight args={['#ffffff', '#a7b5bd', 0.5]} />
        <Sky sunPosition={[5, 3, 5]} turbidity={6} />
        <SunroomModel />
        <ContactShadows position={[0, -0.08, 0]} opacity={0.28} blur={2.2} scale={22} far={10} />
        <OrbitControls enablePan={true} minDistance={8} maxDistance={28} maxPolarAngle={Math.PI / 2.05} />
      </Canvas>
    </div>
  );
}
