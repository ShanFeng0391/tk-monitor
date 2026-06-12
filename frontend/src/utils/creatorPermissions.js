/** 是否可删除/采集该博主（由后端 can_delete 字段决定） */
export function canManageCreator(creator) {
  return creator?.can_delete === true
}
