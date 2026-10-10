from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.mapper.base_personal_todo_mapper import BasePersonalTodoMapper
from app.model.personal_todo import PersonalTodo


class PersonalTodoService:
    def __init__(self, mapper: BasePersonalTodoMapper, owner_id: str) -> None:
        self.mapper = mapper
        self.owner_id = owner_id

    def list_todos(self) -> list[PersonalTodo]:
        return self.mapper.list_all(self.owner_id)

    def create(self, title: str, due_date: date) -> PersonalTodo:
        todo = PersonalTodo(owner_id=self.owner_id, title=title.strip(), due_date=due_date)
        return self.mapper.save(todo)

    def toggle(self, todo_id: str) -> PersonalTodo:
        todo = self.mapper.find_by_id(todo_id, self.owner_id)
        if todo is None:
            raise LookupError("待办不存在")
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        todo.completed_at = None if todo.completed_at else now
        todo.updated_at = now
        return self.mapper.save(todo)

    def delete(self, todo_id: str) -> bool:
        return self.mapper.delete(todo_id, self.owner_id)
