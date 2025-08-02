import numpy as np
from typing import TypedDict, Any
from google.genai import types, Client as GenAIClient
from pymilvus import MilvusClient, DataType, CollectionSchema, FieldSchema
from pymilvus.milvus_client import IndexParams
from pymilvus.milvus_client.index import IndexParam

from config import (
    MILVUS_ENDPOINT,
    MILVUS_TOKEN,
    GEMINI_API_KEY,
    DEFAULT_COLLECTION_NAME,
)

RETRIEVAL_DOCUMENT_TASK_TYPE = "RETRIEVAL_DOCUMENT"
CODE_RETRIEVAL_QUERY_TASK_TYPE = "CODE_RETRIEVAL_QUERY"

DEFAULT_VECTOR_DIMENSION = 768


class MilvusInsertData(TypedDict):
    """Data structure for inserting into Milvus."""

    vector: list[float]
    filename: str
    start_line: int
    end_line: int


class MilvusResponseData(TypedDict):
    """Response data from Milvus insert operation."""

    insert_count: int
    ids: list[Any]
    timestamp: int


class MilvusResponse(TypedDict):
    """Response from Milvus insert operation."""

    data: MilvusResponseData
    status: dict[str, Any]


class MilvusSearchEntity(TypedDict):
    """Entity data in Milvus search result."""

    filename: str
    start_line: int
    end_line: int


class MilvusSearchResult(TypedDict):
    """Single search result from Milvus."""

    id: int
    distance: float
    entity: MilvusSearchEntity


class EmbeddingManager:
    def __init__(
        self,
        milvus_endpoint: str = MILVUS_ENDPOINT,
        milvus_token: str = MILVUS_TOKEN,
        gemini_api_key: str = GEMINI_API_KEY,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        vector_dimension: int = DEFAULT_VECTOR_DIMENSION,
    ):
        """
        Initialize the EmbeddingManager with Milvus and Gemini clients.

        Args:
            milvus_endpoint (str): Milvus cluster endpoint URL
            milvus_token (str): Milvus authentication token
            gemini_api_key (str): Gemini API key
        """
        self.milvus: MilvusClient = MilvusClient(
            uri=milvus_endpoint, token=milvus_token
        )
        self.gemini: GenAIClient = GenAIClient(api_key=gemini_api_key)
        self.collection_name: str = collection_name
        self.vector_dimension: int = vector_dimension

    def drop_collection(self):
        """
        Drop a Milvus collection if it exists.

        Args:
            collection_name (str): Name of the collection to drop.

        Returns:
            bool: True if collection was dropped, False if it did not exist.
        """
        self.milvus.drop_collection(collection_name=self.collection_name)

    def create_collection_if_not_exists(self) -> bool:
        """
        Create a Milvus collection if it doesn't already exist.

        Returns:
            bool: True if a collection was created, False if it already existed.
        """
        # Check if collection exists
        collections = self.milvus.list_collections()
        if self.collection_name in collections:
            print(f"Collection '{self.collection_name}' already exists")
            return False

        # Collection schema definition
        schema: CollectionSchema = CollectionSchema(
            fields=[
                FieldSchema(
                    name="id",
                    description="ID",
                    dtype=DataType.INT64,
                    is_primary=True,
                    auto_id=True,
                ),
                FieldSchema(
                    name="vector",
                    description="Embedding vector",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=self.vector_dimension,
                ),
                FieldSchema(
                    name="filename",
                    description="Source file name",
                    dtype=DataType.VARCHAR,
                    max_length=255,
                ),
                FieldSchema(
                    name="start_line",
                    description="Starting line number",
                    dtype=DataType.INT16,
                ),
                FieldSchema(
                    name="end_line",
                    description="Ending line number",
                    dtype=DataType.INT16,
                ),
            ],
            enable_dynamic_field=False,
        )
        index_params = IndexParams(
            [
                IndexParam(
                    field_name="vector",
                    index_type="HNSW",
                    index_name="hnsw_index",
                    metric_type="COSINE",
                    M=64,
                    efConstruction=100,
                )
            ]
        )

        self.milvus.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        self.milvus.load_collection(self.collection_name)

        print(f"Created collection '{self.collection_name}'")
        return True

    def get_embedding(
        self, text: str, task_type: str = RETRIEVAL_DOCUMENT_TASK_TYPE
    ) -> list[float]:
        """
        Generate a normalized embedding vector for the given text using the GenAI client.

        Args:
            text (str): The input text to embed.
            task_type (str): The type of task for which the embedding is generated. Default is "RETRIEVAL_DOCUMENT".

        Returns:
            list[float]: The normalized embedding vector.
        """
        result: types.EmbedContentResponse = self.gemini.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=self.vector_dimension,
                task_type=task_type,
            ),
        )
        [embedding_obj] = result.embeddings
        embedding_values_np: np.array = np.array(embedding_obj.values)
        normed_embedding: list[float] = (
            embedding_values_np / np.linalg.norm(embedding_values_np)
        ).tolist()

        return normed_embedding

    def get_embeddings_in_batch(
        self, texts: list[str], task_type: str = RETRIEVAL_DOCUMENT_TASK_TYPE
    ) -> list[list[float]]:
        """
        Generate normalized embedding vectors for a batch of texts using the GenAI client.

        Args:
            texts (list[str]): A list of input texts to embed.
            task_type (str): The type of task for which the embeddings are generated. Default is "RETRIEVAL_DOCUMENT".

        Returns:
            list[list[float]]: A list of normalized embedding vectors.
        """
        result: types.EmbedContentResponse = self.gemini.models.embed_content(
            model="gemini-embedding-001",
            contents=texts,
            config=types.EmbedContentConfig(
                output_dimensionality=self.vector_dimension,
                task_type=task_type,
            ),
        )
        embeddings: list[list[float]] = []
        for embedding_obj in result.embeddings:
            embedding_values_np: np.array = np.array(embedding_obj.values)
            normed_embedding: list[float] = (
                embedding_values_np / np.linalg.norm(embedding_values_np)
            ).tolist()
            embeddings.append(normed_embedding)

        return embeddings

    def insert_embedding(
        self, vector: list[float], filename: str, start_line: int, end_line: int
    ) -> MilvusResponse:
        """
        Insert an embedding vector and associated metadata into a Milvus collection.

        Args:
            vector (list[float]): The embedding vector.
            filename (str): The filename associated with the embedding.
            start_line (int): The starting line number in the file.
            end_line (int): The ending line number in the file.

        Returns:
            MilvusResponse: The response from the Milvus insert operation.
        """
        return self.milvus.insert(
            collection_name=self.collection_name,
            data=[
                MilvusInsertData(
                    vector=vector,
                    filename=filename,
                    start_line=start_line,
                    end_line=end_line,
                )
            ],
        )

    def add_to_vector(
        self, content: str, filename: str, start_line: int, end_line: int
    ):
        """
        Add content to a vector database with associated metadata.

        Args:
            content (str): The text content to be embedded.
            filename (str): The source filename.
            start_line (int): Starting line number of the chunk.
            end_line (int): Ending line number of the chunk.
        """
        embedding_vectors: list[float] = self.get_embedding(
            content, RETRIEVAL_DOCUMENT_TASK_TYPE
        )

        self.insert_embedding(
            vector=embedding_vectors,
            filename=filename,
            start_line=start_line,
            end_line=end_line,
        )

    def add_to_vector_in_batch(
        self, batch_data: list[tuple[str, str, int, int]]
    ) -> MilvusResponse | None:
        """
        Add multiple content items to the vector database in a single batch operation.
        Generates embeddings for all content items asynchronously.

        Args:
            batch_data (list[tuple[str, str, int, int]]): List of tuples containing:
                - content (str): The text content to be embedded
                - filename (str): The source filename
                - start_line (int): Starting line number of the chunk
                - end_line (int): Ending line number of the chunk

        """
        if not batch_data:
            return

        # Run the async function and get the embeddings
        embedding_vectors = self.get_embeddings_in_batch(
            [content for content, _, _, _ in batch_data],
            RETRIEVAL_DOCUMENT_TASK_TYPE,
        )

        # Prepare insert data with the generated embeddings
        insert_data = [
            MilvusInsertData(
                vector=embedding_vector,
                filename=filename,
                start_line=start_line,
                end_line=end_line,
            )
            for embedding_vector, (_, filename, start_line, end_line) in zip(
                embedding_vectors, batch_data
            )
        ]

        # Perform batch insert
        return self.milvus.insert(
            collection_name=self.collection_name,
            data=insert_data,
        )

    def delete_embeddings(self, filename: str):
        self.milvus.delete(
            collection_name=self.collection_name,
            filter=f"filename = '{filename}'",
        )

    def retrieve_vectors_for_question(
        self, question: str, top_k: int = 5, dir_path: str | None = None
    ) -> list[MilvusSearchResult]:
        """
        Retrieve vectors from the collection that are most similar to the question.

        Args:
            question (str): The question to search for similar vectors.
            top_k (int): Number of results to return.

        Returns:
            list[list[MilvusSearchResult]]: List of matching documents with their metadata and similarity scores.
            The outer list represents different queries, while the inner list contains the search results for each query.
        """
        # Generate embedding for the question
        question_embedding = self.get_embedding(
            question, CODE_RETRIEVAL_QUERY_TASK_TYPE
        )

        self.milvus.load_collection(self.collection_name)

        search_kwargs: dict = {}
        if dir_path:
            if dir_path in ("/", ".", "./"):
                dir_path = None
            if dir_path:
                dir_path = dir_path.lstrip("./")
                search_kwargs["filter"] = f"filename like '{dir_path}%'"

        # Perform the search
        results: list[list[dict]] = self.milvus.search(
            collection_name=self.collection_name,
            data=[question_embedding],
            output_fields=["filename", "start_line", "end_line"],
            limit=top_k,
            **search_kwargs,
        )
        if not results or not results[0]:
            return []
        return [*sorted(results[0], key=lambda x: x["distance"])]
