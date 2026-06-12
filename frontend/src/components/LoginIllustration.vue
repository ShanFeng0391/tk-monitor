<template>
  <div class="illustration" @mousemove="onMouseMove">
    <div class="parallax-wrap" :style="parallaxStyle">
      <div class="scene">
        <!-- 紫色 -->
        <div class="char char-purple">
          <div class="face face-purple">
            <div class="eye-row">
              <span class="eye sm anim-1" :class="{ blink: blinkPhase }"><span class="pupil"></span></span>
              <span class="eye sm anim-2" :class="{ blink: blinkPhase }"><span class="pupil"></span></span>
            </div>
            <span class="mouth flat-white"></span>
          </div>
        </div>

        <!-- 黑色 -->
        <div class="char char-black">
          <div class="face face-black">
            <span class="eye lg anim-3" :class="{ blink: blinkPhase }"><span class="pupil"></span></span>
            <span class="eye lg anim-4" :class="{ blink: blinkPhase }"><span class="pupil"></span></span>
          </div>
        </div>

        <!-- 橙色 -->
        <div class="char char-orange">
          <div class="face face-center">
            <div class="eye-row">
              <span class="eye md anim-5" :class="{ blink: blinkPhase }"><span class="pupil"></span></span>
              <span class="eye md anim-6" :class="{ blink: blinkPhase }"><span class="pupil"></span></span>
            </div>
            <span class="mouth smile"></span>
          </div>
        </div>

        <!-- 克莱因蓝 -->
        <div class="char char-blue">
          <div class="face face-blue">
            <div class="eye-row">
              <span class="eye md anim-7" :class="{ blink: blinkPhase }"><span class="pupil"></span></span>
              <span class="eye md anim-8" :class="{ blink: blinkPhase }"><span class="pupil"></span></span>
            </div>
            <span class="mouth beak-light"></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const blinkPhase = ref(false)
const parallaxStyle = ref({})
let blinkTimer

function onMouseMove(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const x = (e.clientX - rect.left) / rect.width - 0.5
  const y = (e.clientY - rect.top) / rect.height - 0.5
  parallaxStyle.value = {
    transform: `translate(${x * 12}px, ${y * 10}px)`,
  }
}

onMounted(() => {
  blinkTimer = setInterval(() => {
    blinkPhase.value = true
    setTimeout(() => { blinkPhase.value = false }, 160)
  }, 3400)
})

onUnmounted(() => clearInterval(blinkTimer))
</script>

<style scoped>
.illustration {
  position: relative;
  width: 100%;
  height: 100%;
  background: #f3f3f3;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.parallax-wrap {
  transition: transform 0.35s ease-out;
}

.scene {
  position: relative;
  width: 340px;
  height: 420px;
  margin-top: 40px;
  animation: groupFloat 5s ease-in-out infinite;
}

.char {
  position: absolute;
}

.char-purple {
  width: 80px;
  height: 248px;
  left: 58px;
  top: 0;
  background: #7b4397;
  border-radius: 6px;
  z-index: 1;
}

.char-black {
  width: 62px;
  height: 210px;
  left: 122px;
  top: 38px;
  background: #111;
  border-radius: 6px;
  z-index: 2;
  transform: rotate(-4deg);
  transform-origin: center bottom;
}

.char-orange {
  width: 158px;
  height: 158px;
  left: 10px;
  top: 168px;
  background: #e8843c;
  border-radius: 50%;
  z-index: 3;
}

.char-blue {
  width: 88px;
  height: 176px;
  left: 168px;
  top: 182px;
  background: #002fa7;
  border-radius: 44px 44px 10px 10px;
  z-index: 4;
}

.face {
  position: absolute;
  inset: 0;
}

.face-purple {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 32px;
  gap: 10px;
}

/* 黑色眼睛上移到块体上 1/4 处 */
.face-black {
  display: flex;
  flex-direction: row;
  justify-content: center;
  align-items: flex-start;
  gap: 12px;
  padding-top: 26px;
}

.face-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding-top: 14px;
  gap: 12px;
}

.face-blue {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 48px 0 0 20px;
  gap: 14px;
}

.eye-row {
  display: flex;
  flex-direction: row;
  gap: 12px;
}

/* ===== 眼睛 + 眼珠 ===== */
.eye {
  position: relative;
  display: block;
  flex-shrink: 0;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.12s ease;
  overflow: visible;
}

.eye.sm { width: 11px; height: 11px; }
.eye.md { width: 14px; height: 14px; }
.eye.lg { width: 18px; height: 18px; }

.pupil {
  position: absolute;
  background: #111;
  border-radius: 50%;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.eye.sm .pupil { width: 5px; height: 5px; }
.eye.md .pupil { width: 6px; height: 6px; }
.eye.lg .pupil { width: 7px; height: 7px; }

.eye.blink {
  transform: scaleY(0.1);
}

.eye.blink .pupil {
  opacity: 0;
}

/* 眼珠灵动微动 — 每只眼错开节奏 */
.anim-1 .pupil { animation: lookA 3.6s ease-in-out infinite; }
.anim-2 .pupil { animation: lookB 4.1s ease-in-out infinite 0.3s; }
.anim-3 .pupil { animation: lookC 3.8s ease-in-out infinite 0.6s; }
.anim-4 .pupil { animation: lookA 4.2s ease-in-out infinite 0.9s; }
.anim-5 .pupil { animation: lookB 3.5s ease-in-out infinite 0.2s; }
.anim-6 .pupil { animation: lookC 3.9s ease-in-out infinite 0.7s; }
.anim-7 .pupil { animation: lookA 4s ease-in-out infinite 0.4s; }
.anim-8 .pupil { animation: lookB 3.7s ease-in-out infinite 0.8s; }

@keyframes lookA {
  0%, 100% { transform: translate(-50%, -50%); }
  30% { transform: translate(-35%, -58%); }
  60% { transform: translate(-62%, -42%); }
}

@keyframes lookB {
  0%, 100% { transform: translate(-50%, -50%); }
  25% { transform: translate(-58%, -48%); }
  55% { transform: translate(-38%, -52%); }
}

@keyframes lookC {
  0%, 100% { transform: translate(-50%, -50%); }
  35% { transform: translate(-42%, -60%); }
  70% { transform: translate(-55%, -45%); }
}

/* ===== 嘴巴 ===== */
.mouth.flat-white {
  width: 16px;
  height: 3px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 2px;
}

.mouth.smile {
  width: 26px;
  height: 13px;
  border: 3px solid #111;
  border-top: none;
  border-radius: 0 0 26px 26px;
  animation: smileWiggle 2.8s ease-in-out infinite;
}

.mouth.beak-light {
  width: 40px;
  height: 3px;
  background: #fff;
  border-radius: 2px;
}

@keyframes smileWiggle {
  0%, 100% { transform: scaleX(1); }
  50% { transform: scaleX(1.08); }
}

@keyframes groupFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}
</style>
