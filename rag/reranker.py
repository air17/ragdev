from langchain_classic.retrievers.document_compressors import LLMListwiseRerank
from langchain_core.documents import Document
from langchain_deepseek import ChatDeepSeek

from rag.snippet_reader import EnrichedSearchResult


def _results_to_documents(results: list[EnrichedSearchResult]) -> list[Document]:
    """
    Converts a list of EnrichedSearchResult into a list of Document objects.

    Each result in the input list is mapped to a Document object,
    where the page content is extracted from the "snippet" field
    of the result and the metadata contains the corresponding
    result index as its "id".

    :param results: The list of EnrichedSearchResult objects to be
        transformed into Document objects.
    :type results: list[EnrichedSearchResult]

    :return: A list of Document objects created from the input search results.
    :rtype: list[Document]
    """
    return [
        Document(
            page_content=result[1]["snippet"],
            metadata={
                "id": result[0],
            },
        )
        for result in enumerate(results)
    ]


def rerank_results(
    query: str, search_results: list[EnrichedSearchResult], max_results: int = 3
) -> list[EnrichedSearchResult]:
    """
    Rerank search results using the Deepseek model based on relevance to the query.

    Args:
        query (str): The original user query
        search_results (list[EnrichedSearchResult]): List of search results to be reranked, expected to have a structure similar to MilvusSearchResult
        max_results (int): Maximum number of results to return after reranking

    Returns:
        list[EnrichedSearchResult]: Reranked search results in order of relevance
    """
    documents: list[Document] = _results_to_documents(search_results)
    reranker = LLMListwiseRerank.from_llm(
        llm=ChatDeepSeek(model="deepseek-chat"), top_n=max_results
    )
    reranked_compressed_docs = reranker.compress_documents(documents, query)
    reranked_results = []
    for doc in reranked_compressed_docs:
        reranked_results.append(search_results[int(doc.metadata["id"])])
    return reranked_results
