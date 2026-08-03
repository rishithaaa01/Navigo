from __future__ import annotations

import hashlib
from collections.abc import Iterable

from app.db import Database
from app.schemas import (
    Coordinates,
    FavoritePlaceRequest,
    FavoritePlaceResponse,
    PlaceSafetyRatingRequest,
    RoadSafetyRatingRequest,
    RouteResponse,
    SafetyCommentRequest,
    SafetyCommentResponse,
    SafetySummaryResponse,
    UserResponse,
)


class CommunityServiceError(Exception):
    pass


class CommunityService:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def add_favorite_place(
        self,
        user: UserResponse,
        request: FavoritePlaceRequest,
    ) -> FavoritePlaceResponse:
        insert_query = """
        INSERT INTO favorite_places (user_id, place_name, address, latitude, longitude)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, latitude, longitude)
        DO UPDATE SET
            place_name = EXCLUDED.place_name,
            address = EXCLUDED.address
        """

        async with self._database.pool.acquire() as connection:
            await connection.execute(
                insert_query,
                user.id,
                request.place_name,
                request.address,
                request.latitude,
                request.longitude,
            )

        favorite = await self.get_favorite_place(
            user.id,
            request.latitude,
            request.longitude,
        )
        if favorite is None:
            raise CommunityServiceError("Unable to save favorite place.")
        return favorite

    async def remove_favorite_place(
        self,
        user_id: int,
        latitude: float,
        longitude: float,
    ) -> None:
        query = """
        DELETE FROM favorite_places
        WHERE user_id = $1 AND latitude = $2 AND longitude = $3
        """

        async with self._database.pool.acquire() as connection:
            await connection.execute(query, user_id, latitude, longitude)

    async def list_favorite_places(self, user_id: int) -> list[FavoritePlaceResponse]:
        query = """
        SELECT id, place_name, address, latitude, longitude
        FROM favorite_places
        WHERE user_id = $1
        ORDER BY created_at DESC
        """

        async with self._database.pool.acquire() as connection:
            rows = await connection.fetch(query, user_id)

        return [
            FavoritePlaceResponse(
                id=int(row["id"]),
                place_name=row["place_name"],
                address=row["address"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
            )
            for row in rows
        ]

    async def get_favorite_place(
        self,
        user_id: int,
        latitude: float,
        longitude: float,
    ) -> FavoritePlaceResponse | None:
        query = """
        SELECT id, place_name, address, latitude, longitude
        FROM favorite_places
        WHERE user_id = $1 AND latitude = $2 AND longitude = $3
        LIMIT 1
        """

        async with self._database.pool.acquire() as connection:
            row = await connection.fetchrow(query, user_id, latitude, longitude)

        if row is None:
            return None

        return FavoritePlaceResponse(
            id=int(row["id"]),
            place_name=row["place_name"],
            address=row["address"],
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
        )

    async def add_place_rating(
        self,
        user: UserResponse,
        request: PlaceSafetyRatingRequest,
    ) -> SafetySummaryResponse:
        query = """
        INSERT INTO place_safety_ratings (
            user_id, place_name, address, latitude, longitude, rating_value, comment
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """

        async with self._database.pool.acquire() as connection:
            await connection.execute(
                query,
                user.id,
                request.place_name,
                request.address,
                request.latitude,
                request.longitude,
                self._rating_to_score(request.rating),
                request.comment,
            )

        return await self.get_place_safety_summary(
            request.latitude,
            request.longitude,
        )

    async def get_place_safety_summary(
        self,
        latitude: float,
        longitude: float,
    ) -> SafetySummaryResponse:
        query = """
        SELECT
            COALESCE(AVG(rating_value / 2.0), 0) AS normalized_score,
            COUNT(*) AS total_ratings
        FROM place_safety_ratings
        WHERE latitude = $1 AND longitude = $2
        """

        async with self._database.pool.acquire() as connection:
            row = await connection.fetchrow(query, latitude, longitude)

        normalized_score = float(row["normalized_score"] or 0)
        total_ratings = int(row["total_ratings"] or 0)
        return self._build_summary(normalized_score, total_ratings)

    async def add_road_rating(
        self,
        user: UserResponse,
        request: RoadSafetyRatingRequest,
    ) -> SafetySummaryResponse:
        segments = self._segments_from_points(request.route_points)
        if not segments:
            raise CommunityServiceError("Route must contain at least one segment.")

        insert_query = """
        INSERT INTO road_segment_ratings (
            user_id, segment_key, start_latitude, start_longitude,
            end_latitude, end_longitude, rating_value, comment
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """

        async with self._database.pool.acquire() as connection:
            async with connection.transaction():
                for segment in segments:
                    await connection.execute(
                        insert_query,
                        user.id,
                        segment["segment_key"],
                        segment["start"].latitude,
                        segment["start"].longitude,
                        segment["end"].latitude,
                        segment["end"].longitude,
                        self._rating_to_score(request.rating),
                        request.comment,
                    )

                await self._refresh_segment_scores(connection, segments)

        return await self.get_road_safety_summary(request.route_points)

    async def get_road_safety_summary(
        self,
        route_points: list[Coordinates],
    ) -> SafetySummaryResponse:
        segments = self._segments_from_points(route_points)
        if not segments:
            return self._build_summary(0, 0)

        segment_keys = [segment["segment_key"] for segment in segments]
        placeholders = ", ".join([f"${i+1}" for i in range(len(segment_keys))])
        query = f"""
        SELECT segment_key, normalized_score, rating_count
        FROM road_segment_safety_scores
        WHERE segment_key IN ({placeholders})
        """

        async with self._database.pool.acquire() as connection:
            rows = await connection.fetch(query, *segment_keys)

        if not rows:
            return self._build_summary(0, 0)

        weighted_score = 0.0
        total_ratings = 0
        matched_segments = 0
        for row in rows:
            weighted_score += float(row["normalized_score"])
            total_ratings += int(row["rating_count"])
            matched_segments += 1

        return self._build_summary(weighted_score / matched_segments, total_ratings)

    async def add_comment(
        self,
        user: UserResponse,
        request: SafetyCommentRequest,
    ) -> SafetyCommentResponse:
        query = """
        INSERT INTO safety_comments (
            user_id, target_type, target_key, place_name, address,
            latitude, longitude, comment
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """

        async with self._database.pool.acquire() as connection:
            comment_id = await connection.fetchval(
                query,
                user.id,
                request.target_type,
                request.target_key,
                request.place_name,
                request.address,
                request.latitude,
                request.longitude,
                request.comment.strip(),
            )

        return SafetyCommentResponse(
            id=int(comment_id),
            user_name=user.full_name,
            target_type=request.target_type,
            target_key=request.target_key,
            comment=request.comment.strip(),
            created_at="just now",
        )

    async def list_comments(
        self,
        target_type: str,
        target_key: str,
    ) -> list[SafetyCommentResponse]:
        query = """
        SELECT c.id, c.target_type, c.target_key, c.comment, c.created_at, u.full_name
        FROM safety_comments c
        INNER JOIN users u ON u.id = c.user_id
        WHERE c.target_type = $1 AND c.target_key = $2
        ORDER BY c.created_at DESC
        LIMIT 20
        """

        async with self._database.pool.acquire() as connection:
            rows = await connection.fetch(query, target_type, target_key)

        return [
            SafetyCommentResponse(
                id=int(row["id"]),
                user_name=row["full_name"],
                target_type=row["target_type"],
                target_key=row["target_key"],
                comment=row["comment"],
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        ]

    async def list_user_comments(
        self,
        user_id: int,
    ) -> list[SafetyCommentResponse]:
        query = """
        SELECT c.id, c.target_type, c.target_key, c.comment, c.created_at, 
               c.place_name, c.address, c.latitude, c.longitude, u.full_name
        FROM safety_comments c
        INNER JOIN users u ON u.id = c.user_id
        WHERE c.user_id = $1
        ORDER BY c.created_at DESC
        LIMIT 50
        """

        async with self._database.pool.acquire() as connection:
            rows = await connection.fetch(query, user_id)

        return [
            SafetyCommentResponse(
                id=int(row["id"]),
                user_name=row["full_name"],
                target_type=row["target_type"],
                target_key=row["target_key"],
                comment=row["comment"],
                created_at=row["created_at"].isoformat(),
                place_name=row.get("place_name"),
                address=row.get("address"),
                latitude=float(row["latitude"]) if row.get("latitude") else None,
                longitude=float(row["longitude"]) if row.get("longitude") else None,
            )
            for row in rows
        ]

    async def list_nearby_comments(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 0.5,
    ) -> list[SafetyCommentResponse]:
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * abs(latitude) if latitude != 0 else 111.0)

        query = """
        SELECT c.id, c.target_type, c.target_key, c.comment, c.created_at, 
               c.place_name, c.address, c.latitude, c.longitude, u.full_name
        FROM safety_comments c
        INNER JOIN users u ON u.id = c.user_id
        WHERE c.latitude BETWEEN $1 AND $2
          AND c.longitude BETWEEN $3 AND $4
        ORDER BY c.created_at DESC
        LIMIT 50
        """

        async with self._database.pool.acquire() as connection:
            rows = await connection.fetch(
                query,
                latitude - lat_delta,
                latitude + lat_delta,
                longitude - lon_delta,
                longitude + lon_delta,
            )

        return [
            SafetyCommentResponse(
                id=int(row["id"]),
                user_name=row["full_name"],
                target_type=row["target_type"],
                target_key=row["target_key"],
                comment=row["comment"],
                created_at=row["created_at"].isoformat(),
                place_name=row.get("place_name"),
                address=row.get("address"),
                latitude=float(row["latitude"]) if row.get("latitude") else None,
                longitude=float(row["longitude"]) if row.get("longitude") else None,
            )
            for row in rows
        ]

    def route_comment_key(self, route_points: Iterable[Coordinates]) -> str:
        serialized = "|".join(
            f"{point.latitude:.5f},{point.longitude:.5f}" for point in route_points
        )
        return hashlib.sha1(serialized.encode("utf-8")).hexdigest()

    def _rating_to_score(self, rating: str) -> int:
        return {
            "unsafe": 0,
            "moderate": 1,
            "safe": 2,
        }[rating]

    def _build_summary(
        self,
        normalized_score: float,
        total_ratings: int,
    ) -> SafetySummaryResponse:
        if total_ratings == 0:
            return SafetySummaryResponse(
                normalizedScore=0,
                safetyBadge="Unrated",
                totalRatingsCount=0,
                averageLabel="No ratings yet",
            )

        if normalized_score >= 0.75:
            badge = "Safe"
        elif normalized_score >= 0.4:
            badge = "Moderate"
        else:
            badge = "Unsafe"

        return SafetySummaryResponse(
            normalizedScore=round(normalized_score, 2),
            safetyBadge=badge,
            totalRatingsCount=total_ratings,
            averageLabel=f"{badge} based on community ratings",
        )

    def _segments_from_points(
        self,
        points: list[Coordinates],
    ) -> list[dict[str, Coordinates | str]]:
        segments: list[dict[str, Coordinates | str]] = []
        for index in range(len(points) - 1):
            start = points[index]
            end = points[index + 1]
            if start.latitude == end.latitude and start.longitude == end.longitude:
                continue
            segments.append(
                {
                    "start": start,
                    "end": end,
                    "segment_key": self._segment_key(start, end),
                }
            )
        return segments

    async def _refresh_segment_scores(
        self,
        connection,
        segments: list[dict[str, Coordinates | str]],
    ) -> None:
        processed_keys: set[str] = set()
        for segment in segments:
            segment_key = str(segment["segment_key"])
            if segment_key in processed_keys:
                continue
            processed_keys.add(segment_key)

            aggregate = await connection.fetchrow(
                """
                SELECT AVG(rating_value / 2.0) AS normalized_score, COUNT(*) AS rating_count
                FROM road_segment_ratings
                WHERE segment_key = $1
                """,
                segment_key,
            )
            normalized_score = float(aggregate["normalized_score"] or 0)
            rating_count = int(aggregate["rating_count"] or 0)
            start = segment["start"]
            end = segment["end"]

            await connection.execute(
                """
                INSERT INTO road_segment_safety_scores (
                    segment_key, start_latitude, start_longitude,
                    end_latitude, end_longitude, normalized_score, rating_count
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (segment_key)
                DO UPDATE SET
                    normalized_score = EXCLUDED.normalized_score,
                    rating_count = EXCLUDED.rating_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                segment_key,
                start.latitude,
                start.longitude,
                end.latitude,
                end.longitude,
                normalized_score,
                rating_count,
            )

    def _segment_key(self, start: Coordinates, end: Coordinates) -> str:
        first = f"{start.latitude:.5f},{start.longitude:.5f}"
        second = f"{end.latitude:.5f},{end.longitude:.5f}"
        return "|".join(sorted([first, second]))
