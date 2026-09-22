"""
Sample demo repositories.

Pre-configured repositories with realistic code examples.
"""

from typing import Dict, List, Any, Optional


# Demo Repository 1: Python FastAPI Backend
DEMO_REPO_FASTAPI = {
    "id": "demo_fastapi_backend",
    "name": "FastAPI Auth Service",
    "description": "A sample authentication microservice built with FastAPI",
    "language": "Python",
    "url": "https://github.com/demo/fastapi-auth",
    "stars": 1234,
    "files": [
        {
            "path": "app/main.py",
            "language": "python",
            "code": '''"""
FastAPI Authentication Service

Main application entry point with API routes.
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI(title="Auth Service", version="1.0.0")

# Security configuration
SECRET_KEY = "your-secret-key-here"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user with username and password."""
    # In production, fetch from database
    user = get_user_from_db(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint - returns JWT token."""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me")
async def read_users_me(token: str = Depends(oauth2_scheme)):
    """Get current user from token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_from_db(username)
    if user is None:
        raise credentials_exception

    return user


def get_user_from_db(username: str) -> Optional[dict]:
    """Fetch user from database."""
    # Simulated database lookup
    if username == "demo":
        return {
            "username": "demo",
            "email": "demo@example.com",
            "hashed_password": get_password_hash("demo123"),
            "is_active": True
        }
    return None
''',
        },
        {
            "path": "app/models.py",
            "language": "python",
            "code": '''"""
Data models for the authentication service.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class User(BaseModel):
    """User model."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserInDB(User):
    """User model with password hash."""
    hashed_password: str


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Data extracted from token."""
    username: Optional[str] = None


class UserCreate(BaseModel):
    """User creation request."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    """User response (without password)."""
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime
''',
        },
        {
            "path": "app/database.py",
            "language": "python",
            "code": '''"""
Database operations for user management.
"""
from typing import Optional, List
from app.models import User, UserInDB, UserCreate
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Simulated in-memory database
USERS_DB: dict[str, UserInDB] = {}


def get_user(username: str) -> Optional[UserInDB]:
    """Retrieve a user by username."""
    return USERS_DB.get(username)


def get_user_by_email(email: str) -> Optional[UserInDB]:
    """Retrieve a user by email."""
    for user in USERS_DB.values():
        if user.email == email:
            return user
    return None


def create_user(user_data: UserCreate) -> UserInDB:
    """Create a new user."""
    if get_user(user_data.username):
        raise ValueError("Username already exists")

    if get_user_by_email(user_data.email):
        raise ValueError("Email already registered")

    hashed_password = pwd_context.hash(user_data.password)

    user = UserInDB(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password
    )

    USERS_DB[user.username] = user
    return user


def update_user(username: str, updates: dict) -> Optional[UserInDB]:
    """Update user information."""
    user = get_user(username)
    if not user:
        return None

    for key, value in updates.items():
        if hasattr(user, key) and key != "hashed_password":
            setattr(user, key, value)

    return user


def delete_user(username: str) -> bool:
    """Delete a user."""
    if username in USERS_DB:
        del USERS_DB[username]
        return True
    return False


def list_users(skip: int = 0, limit: int = 100) -> List[UserInDB]:
    """List all users with pagination."""
    users = list(USERS_DB.values())
    return users[skip : skip + limit]
''',
        },
    ],
}


# Demo Repository 2: React TypeScript Frontend
DEMO_REPO_REACT = {
    "id": "demo_react_dashboard",
    "name": "React Dashboard",
    "description": "Modern dashboard built with React, TypeScript, and Tailwind CSS",
    "language": "TypeScript",
    "url": "https://github.com/demo/react-dashboard",
    "stars": 2567,
    "files": [
        {
            "path": "src/components/Dashboard.tsx",
            "language": "typescript",
            "code": '''/**
 * Main Dashboard Component
 *
 * Displays user metrics, recent activity, and analytics.
 */
import React, { useState, useEffect } from 'react';
import { Card } from './ui/Card';
import { Chart } from './charts/Chart';
import { UserStats } from '../types';
import { fetchUserStats, fetchRecentActivity } from '../api/dashboard';

interface DashboardProps {
    userId: string;
}

export const Dashboard: React.FC<DashboardProps> = ({ userId }) => {
    const [stats, setStats] = useState<UserStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        loadDashboardData();
    }, [userId]);

    const loadDashboardData = async () => {
        try {
            setLoading(true);
            setError(null);

            const [statsData, activityData] = await Promise.all([
                fetchUserStats(userId),
                fetchRecentActivity(userId)
            ]);

            setStats(statsData);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load dashboard');
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return <LoadingSpinner />;
    }

    if (error) {
        return <ErrorMessage message={error} onRetry={loadDashboardData} />;
    }

    return (
        <div className="dashboard-container">
            <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <StatsCard
                    title="Total Users"
                    value={stats?.totalUsers || 0}
                    change={stats?.userGrowth || 0}
                />
                <StatsCard
                    title="Revenue"
                    value={`$${stats?.revenue || 0}`}
                    change={stats?.revenueGrowth || 0}
                />
                <StatsCard
                    title="Active Sessions"
                    value={stats?.activeSessions || 0}
                    change={stats?.sessionGrowth || 0}
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card title="User Activity">
                    <Chart data={stats?.activityData || []} type="line" />
                </Card>

                <Card title="Revenue Trends">
                    <Chart data={stats?.revenueData || []} type="bar" />
                </Card>
            </div>
        </div>
    );
};

const LoadingSpinner: React.FC = () => (
    <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
    </div>
);

interface ErrorMessageProps {
    message: string;
    onRetry: () => void;
}

const ErrorMessage: React.FC<ErrorMessageProps> = ({ message, onRetry }) => (
    <div className="bg-red-50 border border-red-200 rounded p-4">
        <p className="text-red-800 mb-2">{message}</p>
        <button
            onClick={onRetry}
            className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
        >
            Retry
        </button>
    </div>
);

interface StatsCardProps {
    title: string;
    value: string | number;
    change: number;
}

const StatsCard: React.FC<StatsCardProps> = ({ title, value, change }) => {
    const isPositive = change >= 0;

    return (
        <Card>
            <h3 className="text-gray-600 text-sm mb-2">{title}</h3>
            <p className="text-3xl font-bold mb-2">{value}</p>
            <span className={`text-sm ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                {isPositive ? '↑' : '↓'} {Math.abs(change)}%
            </span>
        </Card>
    );
};
''',
        },
        {
            "path": "src/api/dashboard.ts",
            "language": "typescript",
            "code": '''/**
 * Dashboard API client
 *
 * Handles API calls for dashboard data.
 */
import axios from 'axios';
import { UserStats, Activity } from '../types';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export async function fetchUserStats(userId: string): Promise<UserStats> {
    try {
        const response = await axios.get(`${API_BASE_URL}/api/stats/user/${userId}`);
        return response.data;
    } catch (error) {
        console.error('Failed to fetch user stats:', error);
        throw new Error('Unable to load user statistics');
    }
}

export async function fetchRecentActivity(userId: string): Promise<Activity[]> {
    try {
        const response = await axios.get(`${API_BASE_URL}/api/activity/${userId}`);
        return response.data;
    } catch (error) {
        console.error('Failed to fetch recent activity:', error);
        throw new Error('Unable to load recent activity');
    }
}

export async function updateUserPreferences(
    userId: string,
    preferences: Record<string, any>
): Promise<void> {
    await axios.put(`${API_BASE_URL}/api/users/${userId}/preferences`, preferences);
}
''',
        },
        {
            "path": "src/hooks/useAuth.ts",
            "language": "typescript",
            "code": '''/**
 * Authentication hook
 *
 * Manages user authentication state.
 */
import { useState, useEffect, useCallback } from 'react';
import { User } from '../types';
import axios from 'axios';

interface UseAuthResult {
    user: User | null;
    loading: boolean;
    error: string | null;
    login: (username: string, password: string) => Promise<void>;
    logout: () => Promise<void>;
    isAuthenticated: boolean;
}

export function useAuth(): UseAuthResult {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        checkAuthStatus();
    }, []);

    const checkAuthStatus = async () => {
        try {
            const token = localStorage.getItem('auth_token');
            if (!token) {
                setLoading(false);
                return;
            }

            const response = await axios.get('/api/users/me', {
                headers: { Authorization: `Bearer ${token}` }
            });

            setUser(response.data);
        } catch (err) {
            localStorage.removeItem('auth_token');
            setError('Session expired');
        } finally {
            setLoading(false);
        }
    };

    const login = useCallback(async (username: string, password: string) => {
        try {
            setLoading(true);
            setError(null);

            const response = await axios.post('/api/token', {
                username,
                password
            });

            localStorage.setItem('auth_token', response.data.access_token);
            await checkAuthStatus();
        } catch (err) {
            setError('Invalid credentials');
            throw err;
        } finally {
            setLoading(false);
        }
    }, []);

    const logout = useCallback(async () => {
        localStorage.removeItem('auth_token');
        setUser(null);
    }, []);

    return {
        user,
        loading,
        error,
        login,
        logout,
        isAuthenticated: !!user
    };
}
''',
        },
    ],
}


# Demo Repository 3: Full-Stack E-commerce (smaller example)
DEMO_REPO_ECOMMERCE = {
    "id": "demo_ecommerce_api",
    "name": "E-commerce API",
    "description": "RESTful API for an e-commerce platform",
    "language": "Python",
    "url": "https://github.com/demo/ecommerce-api",
    "stars": 890,
    "files": [
        {
            "path": "api/products.py",
            "language": "python",
            "code": '''"""
Product management API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from models import Product, ProductCreate, ProductUpdate
from database import db

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/", response_model=List[Product])
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    category: Optional[str] = None,
    search: Optional[str] = None
):
    """List all products with optional filtering."""
    products = db.get_products(skip=skip, limit=limit, category=category, search=search)
    return products


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str):
    """Get a specific product by ID."""
    product = db.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/", response_model=Product, status_code=201)
async def create_product(product: ProductCreate):
    """Create a new product."""
    return db.create_product(product)


@router.put("/{product_id}", response_model=Product)
async def update_product(product_id: str, product: ProductUpdate):
    """Update an existing product."""
    updated = db.update_product(product_id, product)
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found")
    return updated


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: str):
    """Delete a product."""
    deleted = db.delete_product(product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
''',
        },
    ],
}


# All demo repositories
DEMO_REPOSITORIES: Dict[str, Dict[str, Any]] = {
    "demo_fastapi_backend": DEMO_REPO_FASTAPI,
    "demo_react_dashboard": DEMO_REPO_REACT,
    "demo_ecommerce_api": DEMO_REPO_ECOMMERCE,
}


def get_demo_repo(repo_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a demo repository by ID.

    Converts the files list format to a dict format for the data loader.
    """
    repo = DEMO_REPOSITORIES.get(repo_id)
    if not repo:
        return None

    # Convert files list to dict
    repo_copy = repo.copy()
    files_list = repo.get("files", [])
    files_dict = {}

    for file_item in files_list:
        file_path = file_item.get("path")
        file_code = file_item.get("code")
        if file_path and file_code:
            files_dict[file_path] = file_code

    repo_copy["files"] = files_dict
    return repo_copy


def list_demo_repos() -> List[str]:
    """List all demo repository IDs."""
    return list(DEMO_REPOSITORIES.keys())
