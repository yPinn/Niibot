export function stepForFieldPath(path: string): number {
  if (path === 'name' || path.startsWith('package.name') || path.startsWith('world.')) {
    return path.startsWith('world.story_stage') ? 2 : 0
  }
  if (path.startsWith('character.relationships') || path.startsWith('character.knowledge')) {
    return 3
  }
  if (path.startsWith('character.')) return 1
  if (
    path.startsWith('scene.location') ||
    path.startsWith('scene.current_activity') ||
    path.startsWith('scene.current_goal') ||
    path.startsWith('scene.emotional_baseline')
  ) {
    return 2
  }
  if (path.startsWith('scene.')) return 4
  if (
    path.startsWith('package.lore_entries') ||
    path.startsWith('package.examples') ||
    path.startsWith('lore_entries') ||
    path.startsWith('example_replies')
  ) {
    return 5
  }
  return 6
}
