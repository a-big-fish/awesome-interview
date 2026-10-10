from app.mapper.base_personal_todo_mapper import BasePersonalTodoMapper
from app.model.personal_todo import PersonalTodo


class MemoryPersonalTodoMapper(BasePersonalTodoMapper):
    def __init__(self) -> None:
        self._todos: dict[str, PersonalTodo] = {}

    def save(self, todo: PersonalTodo) -> PersonalTodo:
        self._todos[todo.id] = todo.model_copy(deep=True)
        return todo.model_copy(deep=True)

    def find_by_id(self, todo_id: str, owner_id: str) -> PersonalTodo | None:
        todo = self._todos.get(todo_id)
        return todo.model_copy(deep=True) if todo and todo.owner_id == owner_id else None

    def list_all(self, owner_id: str) -> list[PersonalTodo]:
        return sorted((todo.model_copy(deep=True) for todo in self._todos.values()
                       if todo.owner_id == owner_id), key=lambda item: (item.due_date, item.created_at))

    def delete(self, todo_id: str, owner_id: str) -> bool:
        if self.find_by_id(todo_id, owner_id) is None:
            return False
        del self._todos[todo_id]
        return True
