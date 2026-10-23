import js from '@eslint/js';
import react from 'eslint-plugin-react';
import hooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

export default [
  { ignores: ['dist/'] },
  js.configs.recommended,
  react.configs.flat.recommended,
  react.configs.flat['jsx-runtime'],
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: { globals: globals.browser },
    settings: { react: { version: 'detect' } },
    plugins: { 'react-hooks': hooks },
    rules: {
      ...hooks.configs.recommended.rules,
      'react/prop-types': 'off', // props are documented at each component; no PropTypes runtime
      'react/no-unescaped-entities': 'off', // apostrophes in copy render fine
      'no-unused-vars': ['error', { varsIgnorePattern: '^_', ignoreRestSiblings: true }],
    },
  },
];
