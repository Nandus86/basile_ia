import { mdiFileOutline, mdiHomeOutline, mdiChartTimelineVariant, mdiRocketLaunchOutline } from '@mdi/js'

export default [
  {
    title: 'Home',
    icon: mdiHomeOutline,
    to: { name: 'Dashboard' },
  },
  {
    title: 'Acompanhamento',
    icon: mdiChartTimelineVariant,
    to: { name: 'Acompanhamento' },
  },
  {
    title: 'Agents',
    icon: mdiFileOutline,
    to: { name: 'Agents' },
  },
  {
    title: 'Disparador',
    icon: mdiRocketLaunchOutline,
    to: { name: 'Disparador' },
  },
]
