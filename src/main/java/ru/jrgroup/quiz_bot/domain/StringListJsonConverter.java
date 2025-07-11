package ru.jrgroup.quiz_bot.domain;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.util.List;

/**
 * Конвертер для сериализации/десериализации списка строк в JSON (для хранения в JSONB).
 */
@Converter
public class StringListJsonConverter implements AttributeConverter<List<String>, String> {
	private static final ObjectMapper objectMapper = new ObjectMapper();

	@Override
	public String convertToDatabaseColumn(List<String> attribute) {
		try {
			return attribute == null ? "[]" : objectMapper.writeValueAsString(attribute);
		} catch (Exception e) {
			throw new IllegalArgumentException("Could not serialize list", e);
		}
	}

	@Override
	public List<String> convertToEntityAttribute(String dbData) {
		try {
			if (dbData == null) return null;
			return objectMapper.readValue(dbData, new TypeReference<List<String>>() {});
		} catch (Exception e) {
			throw new IllegalArgumentException("Could not deserialize list", e);
		}
	}
}
