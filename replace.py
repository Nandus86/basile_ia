import sys

with open('frontend/src/layouts/DefaultLayout.vue', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "  { title: 'Meus Agentes', icon: 'mdi-robot-outline', to: '/agents' },\n  { title: 'Conhecimento', icon: 'mdi-book-open-page-variant-outline', to: '/documents' },",
    "  { title: 'Meus Agentes', icon: 'mdi-robot-outline', to: '/agents' },\n  { title: 'Disparador', icon: 'mdi-rocket-launch-outline', to: '/disparador' },\n  { title: 'Conhecimento', icon: 'mdi-book-open-page-variant-outline', to: '/documents' },"
)

content = content.replace(
    "  '/agents': 'Meus Agentes',\n  '/documents': 'Base de Conhecimento',",
    "  '/agents': 'Meus Agentes',\n  '/disparador': 'Disparador',\n  '/documents': 'Base de Conhecimento',"
)

with open('frontend/src/layouts/DefaultLayout.vue', 'w', encoding='utf-8') as f:
    f.write(content)
