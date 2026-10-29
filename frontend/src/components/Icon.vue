<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 15 },
  stroke: { type: [Number, String], default: 1.7 },
})

const PATHS = {
  folder: 'M3 6.5A1.5 1.5 0 0 1 4.5 5h3.2l1.4 1.8h5.4A1.5 1.5 0 0 1 16 8.3v5.2A1.5 1.5 0 0 1 14.5 15h-10A1.5 1.5 0 0 1 3 13.5v-7Z',
  users: 'M6.5 9.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Zm6.5-.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM1.8 15c0-2.2 2.1-4 4.7-4s4.7 1.8 4.7 4M12 10.6c2 .2 3.5 1.7 3.5 3.6',
  sliders: 'M3 5h8M14 5h3M3 10h3M9 10h8M3 15h8M14 15h3M13 3v4M7 8v4M13 13v4',
  search: 'M12.5 12.5 16 16M13.8 8.9a4.9 4.9 0 1 1-9.8 0 4.9 4.9 0 0 1 9.8 0Z',
  plus: 'M8 3.5v9M3.5 8h9',
  external: 'M9.5 3.5H13V7M13 3.5 7.5 9M11 12.5H4.5V4.5',
  copy: 'M6.5 6.5V3.8c0-.7.6-1.3 1.3-1.3h4.4c.7 0 1.3.6 1.3 1.3v4.9c0 .7-.6 1.3-1.3 1.3H7.8c-.7 0-1.3-.6-1.3-1.3ZM3.5 7.5h5.2c.7 0 1.3.6 1.3 1.3v4.4c0 .7-.6 1.3-1.3 1.3H3.5c-.7 0-1.3-.6-1.3-1.3V8.8c0-.7.6-1.3 1.3-1.3Z',
  trash: 'M3.5 4.5h9M6 4.5V3h4v1.5M4.6 4.5l.5 8.2c0 .6.5 1 1.1 1h3.6c.6 0 1-.4 1.1-1l.5-8.2',
  clock: 'M8 4.2V8l2.6 1.6M13.8 8a5.8 5.8 0 1 1-11.6 0 5.8 5.8 0 0 1 11.6 0Z',
  download: 'M8 3v7M5.2 7.4 8 10.2l2.8-2.8M3.5 12.5h9',
  close: 'M4.5 4.5l7 7M11.5 4.5l-7 7',
  chevron: 'M5 6.5 8 9.5l3-3',
  check: 'M3.5 8.5 6.4 11.4 12.5 5',
  more: 'M4 8h.01M8 8h.01M12 8h.01',
  logout: 'M6 3.5H4.2c-.7 0-1.2.5-1.2 1.2v6.6c0 .7.5 1.2 1.2 1.2H6M10 5.5 12.5 8 10 10.5M12 8H6',
  refresh: 'M12.8 6.4A5 5 0 1 0 13 9.5M12.8 3.2v3.4h-3.4',
  eye: 'M1.8 8s2.2-4 6.2-4 6.2 4 6.2 4-2.2 4-6.2 4-6.2-4-6.2-4Zm6.2 1.6a1.6 1.6 0 1 0 0-3.2 1.6 1.6 0 0 0 0 3.2Z',
  edit: 'M10.6 2.9 13 5.3 6.4 11.9l-3 .7.7-3 6.5-6.7Z',
  key: 'M9.8 6.2a2.9 2.9 0 1 1-2.1 4.9l-1 1v1.3H5.3v1.4H3.5v-1.9l3.1-3.1a2.9 2.9 0 0 1 3.2-3.6Z',
  layers: 'M8 2.8 13.5 6 8 9.2 2.5 6 8 2.8ZM3 8.6 8 11.4l5-2.8M3 11.2l5 2.8 5-2.8',
  menu: 'M3 4.5h10M3 8h10M3 11.5h10',
  inbox: 'M2.8 9.5h3l.8 1.6h2.8l.8-1.6h3M2.8 9.5 4.3 4h7.4l1.5 5.5v2.2c0 .7-.6 1.3-1.3 1.3H4.1c-.7 0-1.3-.6-1.3-1.3V9.5Z',
}

const d = computed(() => PATHS[props.name] || PATHS.folder)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 16 16"
    fill="none"
    :stroke-width="stroke"
    stroke="currentColor"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="d" />
  </svg>
</template>
