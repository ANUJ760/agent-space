"use client";

import React, { useEffect, useRef } from "react";
import * as THREE from "three";

interface AuthThreeAnimationProps {
  mode?: "signin" | "signup" | "admin";
  className?: string;
  size?: number;
}

/**
 * AuthThreeAnimation
 *
 * An interactive, lightweight 3D cybernetic core built with Three.js.
 * Features an inner wireframe collaboration node, dual counter-rotating
 * orbital particle rings (cyan for humans, violet for autonomous agents),
 * and interactive cursor reaction.
 */
export function AuthThreeAnimation({
  mode = "signin",
  className = "",
  size = 140,
}: AuthThreeAnimationProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  useEffect(() => {
    const container = mountRef.current;
    if (!container || typeof window === "undefined") return;

    // WebGL capability check
    try {
      const canvas = document.createElement("canvas");
      if (
        !window.WebGLRenderingContext ||
        (!canvas.getContext("webgl") && !canvas.getContext("experimental-webgl"))
      ) {
        return;
      }
    } catch {
      return;
    }

    const width = size;
    const height = size;

    // 1. Scene & Camera
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.z = 5.2;

    // 2. Renderer
    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    // 3. Color Palette based on mode (High Contrast Neon/Vivid)
    const isSpecialAdmin = modeRef.current === "admin";
    const primaryColor = isSpecialAdmin ? new THREE.Color("#fbbf24") : new THREE.Color("#00f0ff"); // Vivid Gold / Neon Cyan
    const secondaryColor = isSpecialAdmin ? new THREE.Color("#f43f5e") : new THREE.Color("#b026ff"); // Rose / Electric Violet

    // 4. Core Geometry (Icosahedron wireframe)
    const coreGeometry = new THREE.IcosahedronGeometry(1.25, 1);
    const coreMaterial = new THREE.MeshBasicMaterial({
      color: primaryColor,
      wireframe: true,
      transparent: true,
      opacity: 0.75,
    });
    const coreMesh = new THREE.Mesh(coreGeometry, coreMaterial);
    scene.add(coreMesh);

    // 5. Inner pulsing jewel / core sphere
    const innerGeometry = new THREE.SphereGeometry(0.58, 16, 16);
    const innerMaterial = new THREE.MeshBasicMaterial({
      color: secondaryColor,
      wireframe: true,
      transparent: true,
      opacity: 0.65,
    });
    const innerMesh = new THREE.Mesh(innerGeometry, innerMaterial);
    scene.add(innerMesh);

    // 6. Orbital Ring 1: Human Nodes / Primary (Tilted)
    const ring1Count = 52;
    const ring1Positions = new Float32Array(ring1Count * 3);
    const ring1Radius = 2.15;
    for (let i = 0; i < ring1Count; i++) {
      const angle = (i / ring1Count) * Math.PI * 2;
      ring1Positions[i * 3] = Math.cos(angle) * ring1Radius;
      ring1Positions[i * 3 + 1] = Math.sin(angle) * ring1Radius * 0.42;
      ring1Positions[i * 3 + 2] = Math.sin(angle) * ring1Radius * 0.92;
    }
    const ring1Geometry = new THREE.BufferGeometry();
    ring1Geometry.setAttribute("position", new THREE.BufferAttribute(ring1Positions, 3));
    const ring1Material = new THREE.PointsMaterial({
      color: primaryColor,
      size: 0.11,
      transparent: true,
      opacity: 1.0,
    });
    const ring1Points = new THREE.Points(ring1Geometry, ring1Material);
    scene.add(ring1Points);

    // 7. Orbital Ring 2: Agent Nodes / Secondary (Counter-tilted)
    const ring2Count = 52;
    const ring2Positions = new Float32Array(ring2Count * 3);
    const ring2Radius = 2.45;
    for (let i = 0; i < ring2Count; i++) {
      const angle = (i / ring2Count) * Math.PI * 2;
      ring2Positions[i * 3] = Math.cos(angle) * ring2Radius;
      ring2Positions[i * 3 + 1] = -Math.sin(angle) * ring2Radius * 0.52;
      ring2Positions[i * 3 + 2] = Math.sin(angle) * ring2Radius * 0.88;
    }
    const ring2Geometry = new THREE.BufferGeometry();
    ring2Geometry.setAttribute("position", new THREE.BufferAttribute(ring2Positions, 3));
    const ring2Material = new THREE.PointsMaterial({
      color: secondaryColor,
      size: 0.11,
      transparent: true,
      opacity: 1.0,
    });
    const ring2Points = new THREE.Points(ring2Geometry, ring2Material);
    scene.add(ring2Points);

    // 8. Interactive Mouse Movement
    let mouseX = 0;
    let mouseY = 0;
    let targetX = 0;
    let targetY = 0;

    const handleMouseMove = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      targetX = (e.clientX - centerX) / (window.innerWidth / 2);
      targetY = (e.clientY - centerY) / (window.innerHeight / 2);
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });

    // 9. Animation Loop
    let animationFrameId: number;
    let clock = new THREE.Clock();
    let speedMultiplier = 1.0;

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const delta = clock.getDelta();
      const elapsedTime = clock.getElapsedTime();

      // Smooth mouse easing
      mouseX += (targetX - mouseX) * 0.05;
      mouseY += (targetY - mouseY) * 0.05;

      // Rotate core
      coreMesh.rotation.y += 0.4 * delta * speedMultiplier;
      coreMesh.rotation.x = mouseY * 0.4;
      coreMesh.rotation.z = mouseX * 0.4;

      // Pulse inner core scale
      const pulse = 1 + Math.sin(elapsedTime * 2.5) * 0.08;
      innerMesh.scale.set(pulse, pulse, pulse);
      innerMesh.rotation.y -= 0.6 * delta * speedMultiplier;

      // Counter-rotate rings
      ring1Points.rotation.y += 0.5 * delta * speedMultiplier;
      ring1Points.rotation.x = Math.sin(elapsedTime * 0.5) * 0.2 + mouseY * 0.3;

      ring2Points.rotation.y -= 0.35 * delta * speedMultiplier;
      ring2Points.rotation.z = Math.cos(elapsedTime * 0.5) * 0.2 + mouseX * 0.3;

      renderer.render(scene, camera);
    };

    animate();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("mousemove", handleMouseMove);
      renderer.dispose();
      coreGeometry.dispose();
      coreMaterial.dispose();
      innerGeometry.dispose();
      innerMaterial.dispose();
      ring1Geometry.dispose();
      ring1Material.dispose();
      ring2Geometry.dispose();
      ring2Material.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [size]);

  return (
    <div
      ref={mountRef}
      className={`relative flex items-center justify-center pointer-events-none select-none ${className}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  );
}
