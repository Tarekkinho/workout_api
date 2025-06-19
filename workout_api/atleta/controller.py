from datetime import datetime
from uuid import uuid4
from typing import Optional, List

from fastapi import APIRouter, Body, HTTPException, status, Query
from pydantic import UUID4

from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from fastapi_pagination import Page, add_pagination
from fastapi_pagination.ext.sqlalchemy import paginate

from workout_api.atleta.schemas import AtletaIn, AtletaOut, AtletaUpdate
from workout_api.atleta.models import AtletaModel
from workout_api.categorias.models import CategoriaModel
from workout_api.centro_treinamento.models import CentroTreinamentoModel
from workout_api.contrib.dependencies import DatabaseDependency


router = APIRouter()


class AtletaResumo(AtletaOut):
    nome: str
    centro_treinamento: str
    categoria: str

    class Config:
        orm_mode = True


@router.post(
    '/',
    summary='Criar um novo atleta',
    status_code=status.HTTP_201_CREATED,
    response_model=AtletaOut,
)
async def criar_atleta(
    db_session: DatabaseDependency,
    atleta_in: AtletaIn = Body(...),
):
    # Verifica categoria
    categoria_nome = atleta_in.categoria.nome
    categoria = (await db_session.execute(
        select(CategoriaModel).filter_by(nome=categoria_nome)
    )).scalars().first()

    if not categoria:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'A categoria {categoria_nome} não foi encontrada.',
        )

    # Verifica centro de treinamento
    centro_nome = atleta_in.centro_treinamento.nome
    centro = (await db_session.execute(
        select(CentroTreinamentoModel).filter_by(nome=centro_nome)
    )).scalars().first()

    if not centro:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'O centro de treinamento {centro_nome} não foi encontrado.',
        )

    try:
        # Cria o objeto atleta_model para salvar no banco
        atleta_out = AtletaOut(id=uuid4(), created_at=datetime.utcnow(), **atleta_in.model_dump())
        atleta_model = AtletaModel(**atleta_out.model_dump(exclude={'categoria', 'centro_treinamento'}))

        atleta_model.categoria_id = categoria.pk_id
        atleta_model.centro_treinamento_id = centro.pk_id

        db_session.add(atleta_model)
        await db_session.commit()
        await db_session.refresh(atleta_model)

        # Retorna a saída formatada (incluindo categoria e centro)
        atleta_out = AtletaOut.model_validate(atleta_model)
        return atleta_out

    except IntegrityError as e:
        await db_session.rollback()
        if 'cpf' in str(e.orig).lower():
            raise HTTPException(
                status_code=303,
                detail=f'Já existe um atleta cadastrado com o cpf: {atleta_in.cpf}',
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Ocorreu um erro ao inserir os dados no banco',
            )


@router.get(
    '/',
    summary='Listar atletas com filtros, resumo e paginação',
    response_model=Page[AtletaResumo],
    status_code=status.HTTP_200_OK,
)
async def listar_atletas(
    db_session: DatabaseDependency,
    nome: Optional[str] = Query(None, description='Filtrar por nome'),
    cpf: Optional[str] = Query(None, description='Filtrar por CPF'),
):
    query = select(AtletaModel).join(CategoriaModel).join(CentroTreinamentoModel)

    if nome:
        query = query.filter(AtletaModel.nome.ilike(f'%{nome}%'))
    if cpf:
        query = query.filter(AtletaModel.cpf == cpf)

    # Usa a paginação fastapi-pagination
    resultados = await paginate(db_session, query)

    # Mapear resultado para AtletaResumo manualmente para incluir centro e categoria nome
    for item in resultados.items:
        item.categoria = item.categoria.nome
        item.centro_treinamento = item.centro_treinamento.nome

    return resultados


@router.get(
    '/{id}',
    summary='Consultar um atleta pelo id',
    response_model=AtletaOut,
    status_code=status.HTTP_200_OK,
)
async def consultar_atleta(
    id: UUID4,
    db_session: DatabaseDependency,
):
    atleta = (await db_session.execute(
        select(AtletaModel).filter_by(id=id)
    )).scalars().first()

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Atleta não encontrado no id: {id}',
        )

    return AtletaOut.model_validate(atleta)


@router.patch(
    '/{id}',
    summary='Atualizar um atleta pelo id',
    response_model=AtletaOut,
    status_code=status.HTTP_200_OK,
)
async def atualizar_atleta(
    id: UUID4,
    db_session: DatabaseDependency,
    atleta_update: AtletaUpdate = Body(...),
):
    atleta = (await db_session.execute(
        select(AtletaModel).filter_by(id=id)
    )).scalars().first()

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Atleta não encontrado no id: {id}',
        )

    update_data = atleta_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(atleta, key, value)

    await db_session.commit()
    await db_session.refresh(atleta)

    return AtletaOut.model_validate(atleta)


@router.delete(
    '/{id}',
    summary='Deletar um atleta pelo id',
    status_code=status.HTTP_204_NO_CONTENT,
)
async def deletar_atleta(
    id: UUID4,
    db_session: DatabaseDependency,
):
    atleta = (await db_session.execute(
        select(AtletaModel).filter_by(id=id)
    )).scalars().first()

    if not atleta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Atleta não encontrado no id: {id}',
        )

    await db_session.delete(atleta)
    await db_session.commit()
    return None


# Adiciona paginação ao router
add_pagination(router)
