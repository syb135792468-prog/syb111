export type SlideStyle = 'python-blue' | 'dark-premium' | 'keynote'

export const SLIDE_STYLES: { value: SlideStyle; label: string; desc: string }[] = [
  { value: 'python-blue', label: 'Python 蓝', desc: '默认教育风格，明亮清新' },
  { value: 'dark-premium', label: '暗夜尊享', desc: '黑底金调，奢华质感' },
  { value: 'keynote', label: 'Keynote', desc: 'Apple 风格，纯黑居中' },
]
