# FastAPI Standards

## Route Definition
```python
@router.post("/resource", response_model=ResourceResponse, status_code=201)
async def create_resource(
    data: ResourceCreate,
    service: ResourceService = Depends(get_resource_service),
    current_user: User = Depends(get_current_user),
) -> ResourceResponse:
    """Create a new resource. Requires authentication."""
    return await service.create(data, user_id=current_user.id)
```

## Service Layer
- All business logic lives in services
- Services are injected via FastAPI Depends
- Services call repositories for data access
- Services handle error cases and raise HTTPException

## Error Handling
```python
from fastapi import HTTPException, status

if not resource:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Resource {resource_id} not found",
    )
```

## Dependency Injection
```python
async def get_resource_service(
    db: AsyncSession = Depends(get_db),
) -> ResourceService:
    return ResourceService(db=db)
```
