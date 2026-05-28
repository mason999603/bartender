"""Pydantic models — shared across routers."""
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Chat ----
class ChatRequest(BaseModel):
    session_id: str = "main"
    message: str


class ChatResponse(BaseModel):
    session_id: str
    user_message: str
    reply: str
    timestamp: str


class StoredMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str  # 'user' | 'russell'
    content: str
    timestamp: str = Field(default_factory=now_iso)


# ---- Cocktails ----
class CocktailIngredient(BaseModel):
    name: str
    amount_ml: float = 0
    notes: Optional[str] = None


class Cocktail(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category: str = "other"
    glassware: str = ""
    garnish: str = ""
    method: str = ""
    ingredients: List[CocktailIngredient] = []
    instructions: str = ""
    flavor_profile: List[str] = []
    abv_estimate: float = 0
    tags: List[str] = []
    is_custom: bool = False
    created_at: str = Field(default_factory=now_iso)


class CocktailCreate(BaseModel):
    name: str
    category: str = "custom"
    glassware: str = ""
    garnish: str = ""
    method: str = ""
    ingredients: List[CocktailIngredient] = []
    instructions: str = ""
    flavor_profile: List[str] = []
    abv_estimate: float = 0
    tags: List[str] = []


class IngredientsQuery(BaseModel):
    ingredients: List[str]


class FlavourQuery(BaseModel):
    include: List[str] = []
    exclude: List[str] = []
    limit: int = 30


class CompatibilityQuery(BaseModel):
    ingredients: List[str]


class BatchRequest(BaseModel):
    cocktail_id: Optional[str] = None
    ingredients: Optional[List[CocktailIngredient]] = None
    servings: int = 10
    dilution_pct: float = 0


class AbvIngredient(BaseModel):
    name: str
    amount_ml: float
    abv: float


class AbvRequest(BaseModel):
    ingredients: List[AbvIngredient]
    dilution_ml: float = 0


class CostIngredient(BaseModel):
    name: str
    amount_ml: float
    price_per_litre: float


class CostRequest(BaseModel):
    ingredients: List[CostIngredient]
    extra_cost: float = 0


# ---- Admin (regulars, memory, inventory) ----
class Regular(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    likes: List[str] = []
    dislikes: List[str] = []
    favourite_cocktails: List[str] = []
    notes: str = ""
    created_at: str = Field(default_factory=now_iso)


class RegularCreate(BaseModel):
    name: str
    likes: List[str] = []
    dislikes: List[str] = []
    favourite_cocktails: List[str] = []
    notes: str = ""


class Memory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key: str
    value: str
    created_at: str = Field(default_factory=now_iso)


class MemoryCreate(BaseModel):
    key: str
    value: str


class InventoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    in_stock: bool = True
    notes: str = ""


class InventoryCreate(BaseModel):
    name: str
    in_stock: bool = True
    notes: str = ""


# ---- Collections ----
class CollectionItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    subtitle: str = ""
    tags: List[str] = []
    notes: str = ""
    rating: Optional[int] = None
    created_at: str = Field(default_factory=now_iso)


class Collection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    icon: str = "stack"
    description: str = ""
    items: List[CollectionItem] = []
    created_at: str = Field(default_factory=now_iso)


class CollectionCreate(BaseModel):
    name: str
    icon: str = "stack"
    description: str = ""


class CollectionItemCreate(BaseModel):
    title: str
    subtitle: str = ""
    tags: List[str] = []
    notes: str = ""
    rating: Optional[int] = None


# ---- Companion / Mood ----
class MoodSetting(BaseModel):
    mode: str  # "default" | "service" | "quiet" | "showtime"
