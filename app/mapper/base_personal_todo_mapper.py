from abc import ABC, abstractmethod

from app.model.personal_todo import PersonalTodo


class BasePersonalTodoMapper(ABC):
    @abstractmethod
    def save(self, todo: PersonalTodo) -> PersonalTodo: ...

    @abstractmethod
    def find_by_id(self, todo_id: str, owner_id: str) -> PersonalTodo | None: ...

    @abstractmethod
    def list_all(self, owner_id: str) -> list[PersonalTodo]: ...

    @abstractmethod
    def delete(self, todo_id: str, owner_id: str) -> bool: ...
