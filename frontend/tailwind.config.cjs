// vibello/frontend/tailwind.config.cjs
module.exports = {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  safelist: ['./index.html', './src/**/*.{ks.jsx}'],
  theme: {
    extend: {
      colors: {
        lavender: '#E3D2FF',
        purple: '#AA93FF',
        'dark-purple': '#20093A',
        brown: '#D9D3A7',
      },
    },
  },
  plugins: [],
};