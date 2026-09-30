"use client";

import React, { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import * as THREE from "three";

/**
 * ThreeTransitionCanvas
 *
 * Lightweight, high-performance ambient 3D particle nexus using Three.js.
 * Renders interactive dual-color nodes representing human engineers (cyan)
 * and autonomous agents (violet) with dynamic constellation lines.
 *
 * Automatically triggers a smooth user-friendly wave transition on route changes.
 */
export function ThreeTransitionCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const transitionRef = useRef<{ triggerWave: () => void } | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof window === "undefined") return;

    // Check for WebGL capability
    try {
      const testCanvas = document.createElement("canvas");
      if (!window.WebGLRenderingContext || (!testCanvas.getContext("webgl") && !testCanvas.getContext("experimental-webgl"))) {
        return;
      }
    } catch {
      return;
    }

    // 1. Scene & Camera setup
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      60,
      window.innerWidth / window.innerHeight,
      0.1,
      1000
    );
    camera.position.z = 180;

    // 2. Renderer setup
    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    // 3. Particles data (Dual node types: Humans = Cyan, Agents = Violet)
    const particleCount = 110;
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const velocities: { x: number; y: number; z: number; originX: number; originY: number; originZ: number }[] = [];

    const cyan = new THREE.Color("#06b6d4"); // Human marker
    const violet = new THREE.Color("#8b5cf6"); // Agent marker

    for (let i = 0; i < particleCount; i++) {
      const x = (Math.random() - 0.5) * 320;
      const y = (Math.random() - 0.5) * 220;
      const z = (Math.random() - 0.5) * 120;

      positions[i * 3] = x;
      positions[i * 3 + 1] = y;
      positions[i * 3 + 2] = z;

      // Half humans, half agents
      const col = i % 2 === 0 ? cyan : violet;
      colors[i * 3] = col.r;
      colors[i * 3 + 1] = col.g;
      colors[i * 3 + 2] = col.b;

      velocities.push({
        x: (Math.random() - 0.5) * 0.22,
        y: (Math.random() - 0.5) * 0.22,
        z: (Math.random() - 0.5) * 0.15,
        originX: x,
        originY: y,
        originZ: z,
      });
    }

    const particleGeometry = new THREE.BufferGeometry();
    particleGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    particleGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    // Circle texture for smooth minimalistic circular nodes
    const canvas = document.createElement("canvas");
    canvas.width = 32;
    canvas.height = 32;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.beginPath();
      ctx.arc(16, 16, 14, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff";
      ctx.fill();
    }
    const texture = new THREE.CanvasTexture(canvas);

    const particleMaterial = new THREE.PointsMaterial({
      size: 4.5,
      vertexColors: true,
      map: texture,
      transparent: true,
      opacity: 0.75,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    const particles = new THREE.Points(particleGeometry, particleMaterial);
    scene.add(particles);

    // 4. Dynamic connecting lines
    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0x3b82f6,
      transparent: true,
      opacity: 0.12,
      blending: THREE.AdditiveBlending,
    });

    const maxLines = 150;
    const linePositions = new Float32Array(maxLines * 6);
    const lineGeometry = new THREE.BufferGeometry();
    lineGeometry.setAttribute("position", new THREE.BufferAttribute(linePositions, 3));
    const lines = new THREE.LineSegments(lineGeometry, lineMaterial);
    scene.add(lines);

    // Mouse tilt interaction
    let mouseX = 0;
    let mouseY = 0;
    const onMouseMove = (e: MouseEvent) => {
      mouseX = (e.clientX / window.innerWidth - 0.5) * 20;
      mouseY = (e.clientY / window.innerHeight - 0.5) * 15;
    };
    window.addEventListener("mousemove", onMouseMove);

    // 5. User-friendly Route Transition Wave
    let waveTime = 0;
    let isWaveActive = false;

    const triggerWave = () => {
      waveTime = 0;
      isWaveActive = true;
    };
    transitionRef.current = { triggerWave };

    // 6. Animation loop
    let animationFrameId: number;
    let clock = 0;

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      clock += 0.01;

      // Parallax camera lerp
      camera.position.x += (mouseX - camera.position.x) * 0.03;
      camera.position.y += (-mouseY - camera.position.y) * 0.03;
      camera.lookAt(0, 0, 0);

      // Wave pulse progression
      if (isWaveActive) {
        waveTime += 0.04;
        if (waveTime > Math.PI) {
          isWaveActive = false;
        }
      }
      const waveFactor = isWaveActive ? Math.sin(waveTime) * 1.8 : 0;

      // Particle physics
      const posArray = particleGeometry.attributes.position.array as Float32Array;
      for (let i = 0; i < particleCount; i++) {
        const vel = velocities[i];
        posArray[i * 3] += vel.x + (Math.sin(clock + i) * 0.08) + (vel.x * waveFactor * 4);
        posArray[i * 3 + 1] += vel.y + (Math.cos(clock + i) * 0.08) + (vel.y * waveFactor * 4);
        posArray[i * 3 + 2] += vel.z;

        // Soft boundaries bounce
        if (Math.abs(posArray[i * 3] - vel.originX) > 40) vel.x *= -1;
        if (Math.abs(posArray[i * 3 + 1] - vel.originY) > 30) vel.y *= -1;
        if (Math.abs(posArray[i * 3 + 2] - vel.originZ) > 25) vel.z *= -1;
      }
      particleGeometry.attributes.position.needsUpdate = true;

      // Connect nearby particles with subtle lines
      let lineVertexIndex = 0;
      const connectionDist = 48;
      for (let i = 0; i < particleCount && lineVertexIndex < maxLines * 6; i++) {
        for (let j = i + 1; j < particleCount && lineVertexIndex < maxLines * 6; j++) {
          const dx = posArray[i * 3] - posArray[j * 3];
          const dy = posArray[i * 3 + 1] - posArray[j * 3 + 1];
          const dz = posArray[i * 3 + 2] - posArray[j * 3 + 2];
          const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);

          if (dist < connectionDist) {
            linePositions[lineVertexIndex++] = posArray[i * 3];
            linePositions[lineVertexIndex++] = posArray[i * 3 + 1];
            linePositions[lineVertexIndex++] = posArray[i * 3 + 2];

            linePositions[lineVertexIndex++] = posArray[j * 3];
            linePositions[lineVertexIndex++] = posArray[j * 3 + 1];
            linePositions[lineVertexIndex++] = posArray[j * 3 + 2];
          }
        }
      }
      // Zero out unused line vertices
      for (let i = lineVertexIndex; i < maxLines * 6; i++) {
        linePositions[i] = 0;
      }
      lineGeometry.attributes.position.needsUpdate = true;

      renderer.render(scene, camera);
    };

    animate();

    // 7. Resize handler
    const onResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener("resize", onResize);

    // 8. Cleanup
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(animationFrameId);
      particleGeometry.dispose();
      particleMaterial.dispose();
      lineGeometry.dispose();
      lineMaterial.dispose();
      renderer.dispose();
      if (container && renderer.domElement) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  // Trigger wave on route / pathname changes
  useEffect(() => {
    if (transitionRef.current) {
      transitionRef.current.triggerWave();
    }
  }, [pathname]);

  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      className="fixed inset-0 pointer-events-none z-0 opacity-25 overflow-hidden transition-opacity duration-700 ease-in-out"
    />
  );
}
