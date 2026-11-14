"""GraphQL query documents for the public BirdWeather API."""

STATION = """
query Station($id: ID!) {
  station(id: $id) {
    id
    name
    type
    timezone
    location
    continent
    country
    state
    notes
    coords { lat lon }
    locationPrivacy
    locationPrivacyRadius
    earliestDetectionAt
    latestDetectionAt
    minConfidence
    minProbability
    minScore
    audioUrl
    videoUrl
    edition
    hasProbabilities
  }
}
"""

STATION_COUNTS = """
query StationCounts($id: ID!, $period: InputDuration) {
  station(id: $id) {
    id
    name
    timezone
    counts(period: $period) {
      detections
      species
    }
  }
}
"""

STATION_WEATHER = """
query StationWeather($id: ID!) {
  station(id: $id) {
    id
    name
    timezone
    weather {
      timestamp
      description
      temp
      tempMin
      tempMax
      feelsLike
      humidity
      pressure
      windSpeed
      windDir
      windGust
      cloudiness
      visibility
      rain1h
      rain3h
      snow1h
      snow3h
      sunrise
      sunset
      coords { lat lon }
    }
  }
}
"""

DETECTIONS = """
query StationDetections(
  $id: ID!
  $first: Int
  $after: String
  $period: InputDuration
  $speciesId: ID
  $speciesIds: [ID!]
  $confidenceGte: Float
  $sortBy: String
) {
  station(id: $id) {
    id
    name
    timezone
    detections(
      first: $first
      after: $after
      period: $period
      speciesId: $speciesId
      speciesIds: $speciesIds
      confidenceGte: $confidenceGte
      sortBy: $sortBy
    ) {
      totalCount
      speciesCount
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        timestamp
        confidence
        probability
        score
        certainty
        mode
        speciesId
        species {
          id
          commonName
          scientificName
          imageUrl
          thumbnailUrl
        }
        soundscape { id url startTime endTime duration mode }
      }
    }
  }
}
"""

TOP_SPECIES = """
query StationTopSpecies($id: ID!, $limit: Int, $offset: Int, $period: InputDuration, $speciesId: ID) {
  station(id: $id) {
    id
    name
    timezone
    topSpecies(limit: $limit, offset: $offset, period: $period, speciesId: $speciesId) {
      speciesId
      count
      averageProbability
      species { id commonName scientificName thumbnailUrl }
    }
  }
}
"""

DAILY_COUNTS = """
query DailyCounts($stationIds: [ID!], $speciesIds: [ID!], $period: InputDuration) {
  dailyDetectionCounts(stationIds: $stationIds, speciesIds: $speciesIds, period: $period) {
    date
    dayOfYear
    total
    counts {
      count
      speciesId
      species { id commonName scientificName }
    }
  }
}
"""

SPECIES = """
query Species($id: ID, $scientificName: String) {
  species(id: $id, scientificName: $scientificName) {
    id
    commonName
    scientificName
    classification
    alpha
    alpha6
    ebirdCode
    ebirdUrl
    birdweatherUrl
    wikipediaUrl
    wikipediaSummary
    imageUrl
    thumbnailUrl
    imageCredit
    imageLicense
    imageLicenseUrl
    stationCount
    mlUrl
  }
}
"""

SEARCH_SPECIES = """
query SearchSpecies($query: String!, $first: Int, $after: String) {
  searchSpecies(query: $query, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      commonName
      scientificName
      classification
      thumbnailUrl
      ebirdCode
    }
  }
}
"""

STATIONS = """
query Stations(
  $first: Int
  $after: String
  $query: String
  $ne: InputLocation
  $sw: InputLocation
  $period: InputDuration
) {
  stations(first: $first, after: $after, query: $query, ne: $ne, sw: $sw, period: $period) {
    totalCount
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      name
      type
      timezone
      location
      continent
      country
      state
      coords { lat lon }
      earliestDetectionAt
      latestDetectionAt
    }
  }
}
"""
