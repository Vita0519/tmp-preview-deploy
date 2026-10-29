<script setup>
const props = defineProps({
  values: { type: Array, default: () => [] },
  width: { type: Number, default: 54 },
  height: { type: Number, default: 18 },
})

function bars() {
  const v = props.values.length ? props.values : [0]
  const max = Math.max(...v, 1)
  const gap = 2
  const raw = (props.width - gap * (v.length - 1)) / v.length
  const bw = Math.max(1, Math.min(3.2, raw))
  return v.map((n, i) => {
    const h = Math.max(1.5, (n / max) * props.height)
    return {
      x: i * (bw + gap),
      y: props.height - h,
      w: bw,
      h,
      o: 0.28 + (0.72 * (i + 1)) / v.length,
    }
  })
}
</script>

<template>
  <svg v-if="values.filter((v) => v > 0).length >= 2 || values.length >= 6" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" aria-hidden="true">
    <rect
      v-for="(b, i) in bars()"
      :key="i"
      :x="b.x"
      :y="b.y"
      :width="b.w"
      :height="b.h"
      rx="1"
      fill="var(--brand)"
      :opacity="b.o"
    />
  </svg>
</template>
